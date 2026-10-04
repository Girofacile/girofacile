"""Private delivery-evidence storage.

Production uses S3-compatible object storage. Development may use a local
filesystem backend so POD flows can be tested without external services.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

_EVIDENCE_KEY_RE = re.compile(
    r'companies/\d+/routes/\d+/deliveries/\d+/'
    r'(signature|delivery_photo|pod)-[a-f0-9]{32}\.(png|jpg|pdf)'
)


class StorageUnavailable(HTTPException):
    """Sanitized failure registered by the application's existing error monitor."""


def enabled():
    return os.getenv('OBJECT_STORAGE_ENABLED', 'false').lower() in ('true', '1', 'yes')


def backend():
    return (os.getenv('OBJECT_STORAGE_BACKEND', 's3') or 's3').strip().lower()


def unavailable():
    # Never log provider exceptions: they may contain credentials or signed URLs.
    logger.error('POD object storage unavailable; check configuration and provider health')
    return StorageUnavailable(503, 'Archivio POD non disponibile. Firma e foto non salvate: conserva questa schermata e riprova.')


def _is_development():
    return os.getenv('APP_ENV', 'development').strip().lower() in ('development', 'dev', 'test', 'testing')


def _signed_url_seconds():
    try:
        seconds = int(os.getenv('OBJECT_STORAGE_SIGNED_URL_SECONDS', '900'))
        if not 60 <= seconds <= 900:
            raise ValueError()
        return seconds
    except ValueError:
        raise unavailable() from None


def _validate_s3_endpoint(value):
    endpoint = urlsplit(value)
    if (
        endpoint.scheme != 'https'
        or not endpoint.netloc
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or endpoint.path not in ('', '/')
    ):
        raise ValueError()
    return value.rstrip('/')


def s3_configuration():
    values = {name: os.getenv('OBJECT_STORAGE_' + name, '').strip() for name in
              ('ENDPOINT', 'REGION', 'BUCKET', 'ACCESS_KEY', 'SECRET_KEY')}
    try:
        if not enabled() or not all(values.values()):
            raise ValueError()
        values['ENDPOINT'] = _validate_s3_endpoint(values['ENDPOINT'])
    except ValueError:
        raise unavailable() from None
    return values, _signed_url_seconds()


def local_root():
    raw = os.getenv('OBJECT_STORAGE_LOCAL_PATH', '').strip()
    if raw:
        root = Path(raw).expanduser()
        if not root.is_absolute():
            root = Path(__file__).resolve().parent.parent.parent / root
    else:
        root = Path(__file__).resolve().parent.parent.parent / 'data' / 'pod_storage'
    return root.resolve()


def _local_secret():
    secret = os.getenv('OBJECT_STORAGE_LOCAL_SECRET', '').strip() or os.getenv('APP_SECRET', '').strip()
    if not secret:
        raise unavailable()
    return secret.encode('utf-8')


def scope(company_id, route_id, delivery_id):
    ids = (company_id, route_id, delivery_id)
    if any(not isinstance(i, int) or i <= 0 for i in ids):
        raise HTTPException(404, 'Documento non trovato')
    return f'companies/{company_id}/routes/{route_id}/deliveries/{delivery_id}/'


def object_key(company_id, route_id, delivery_id, kind):
    extension = {'signature': 'png', 'delivery_photo': 'jpg', 'pod': 'pdf'}[kind]
    return scope(company_id, route_id, delivery_id) + f'{kind}-{uuid4().hex}.{extension}'


def validate_key(key, company_id, route_id, delivery_id, kind):
    extension = {'signature': 'png', 'delivery_photo': 'jpg', 'pod': 'pdf'}[kind]
    prefix = scope(company_id, route_id, delivery_id)
    if not isinstance(key, str) or not re.fullmatch(re.escape(prefix + kind + '-') + r'[a-f0-9]{32}\.' + extension, key):
        raise HTTPException(404, 'Documento non trovato')
    return key


def _validate_generic_key(key):
    if not isinstance(key, str) or not _EVIDENCE_KEY_RE.fullmatch(key):
        raise HTTPException(404, 'Documento non trovato')
    return key


class ObjectStorage:
    """Private S3-compatible storage used in production (for example Hetzner)."""

    def __init__(self):
        values, self.seconds = s3_configuration()
        try:
            import boto3
            from botocore.config import Config
            self.bucket = values['BUCKET']
            self._private_checked = False
            self.client = boto3.client(
                's3',
                endpoint_url=values['ENDPOINT'],
                region_name=values['REGION'],
                aws_access_key_id=values['ACCESS_KEY'],
                aws_secret_access_key=values['SECRET_KEY'],
                config=Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'path'},
                    connect_timeout=5,
                    read_timeout=20,
                    retries={'max_attempts': 2},
                ),
            )
        except Exception:
            raise unavailable() from None

    def verify_configuration(self):
        """Refuse public bucket ACLs/policies; never create or configure a bucket."""
        try:
            from botocore.exceptions import ClientError
            acl = self.client.get_bucket_acl(Bucket=self.bucket)
            for grant in acl.get('Grants', []):
                uri = grant.get('Grantee', {}).get('URI', '')
                if uri.endswith(('/AllUsers', '/AuthenticatedUsers')):
                    raise ValueError('Public bucket')
            try:
                policy = json.loads(self.client.get_bucket_policy(Bucket=self.bucket)['Policy'])
            except ClientError as exc:
                if exc.response['Error']['Code'] not in ('NoSuchBucketPolicy', 'NoSuchPolicy'):
                    raise
                policy = {}
            statements = policy.get('Statement', [])
            if isinstance(statements, dict):
                statements = [statements]
            for statement in statements:
                principal = statement.get('Principal', {})
                if statement.get('Effect') == 'Allow' and (
                    principal == '*' or (isinstance(principal, dict) and any(
                        value == '*' or (isinstance(value, list) and '*' in value)
                        for value in principal.values()))):
                    raise ValueError('Public bucket policy')
            self._private_checked = True
        except Exception:
            raise unavailable() from None

    def upload(self, key, raw, content_type):
        if not self._private_checked:
            self.verify_configuration()
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=raw,
                ContentType=content_type,
                Metadata={'sha256': hashlib.sha256(raw).hexdigest()},
            )
        except Exception:
            raise unavailable() from None

    def read(self, key):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            stream = response['Body']
            try:
                raw = stream.read(12_000_001)
            finally:
                stream.close()
            if len(raw) > 12_000_000:
                raise ValueError()
            return raw
        except Exception:
            raise unavailable() from None

    def signed_url(self, key, content_type, download=False):
        if not self._private_checked:
            self.verify_configuration()
        try:
            return self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket,
                    'Key': key,
                    'ResponseContentType': content_type,
                    'ResponseContentDisposition': ('attachment' if download else 'inline') + '; filename="' + key.rsplit('/', 1)[1] + '"',
                },
                ExpiresIn=self.seconds,
            )
        except Exception:
            raise unavailable() from None

    def delete(self, key):
        _validate_generic_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=key)


class LocalObjectStorage:
    """Development-only private filesystem backend.

    Files stay outside PostgreSQL. Access happens through short-lived HMAC links
    served by GiroFacile itself, mirroring the capability-link behavior of S3.
    """

    def __init__(self):
        if not enabled() or not _is_development():
            raise unavailable()
        self.seconds = _signed_url_seconds()
        self.root = local_root()
        self._secret = _local_secret()

    def verify_configuration(self):
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / '.write-test'
            probe.write_bytes(b'ok')
            probe.unlink(missing_ok=True)
        except Exception:
            raise unavailable() from None

    def _path(self, key):
        _validate_generic_key(key)
        path = (self.root / key).resolve()
        try:
            path.relative_to(self.root)
        except ValueError:
            raise HTTPException(404, 'Documento non trovato')
        return path

    def upload(self, key, raw, content_type):
        try:
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + '.tmp-' + uuid4().hex)
            tmp.write_bytes(raw)
            tmp.replace(path)
        except HTTPException:
            raise
        except Exception:
            raise unavailable() from None

    def read(self, key):
        try:
            raw = self._path(key).read_bytes()
            if len(raw) > 12_000_000:
                raise ValueError()
            return raw
        except FileNotFoundError:
            raise HTTPException(404, 'Documento non trovato') from None
        except HTTPException:
            raise
        except Exception:
            raise unavailable() from None

    def signed_url(self, key, content_type, download=False):
        _validate_generic_key(key)
        expires = int(time.time()) + self.seconds
        dl = 1 if download else 0
        payload = f'{key}|{expires}|{dl}'.encode('utf-8')
        signature = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        return '/api/pod-local?' + urlencode({'key': key, 'exp': expires, 'dl': dl, 'sig': signature})

    def delete(self, key):
        try:
            self._path(key).unlink(missing_ok=True)
        except HTTPException:
            raise
        except Exception:
            raise unavailable() from None


def serve_local_object(key, exp, dl, sig):
    """Validate an expiring local-storage capability URL and serve the file."""
    if backend() != 'local' or not _is_development():
        raise HTTPException(404, 'Documento non trovato')
    _validate_generic_key(key)
    try:
        expires = int(exp)
        download = 1 if int(dl) else 0
    except (TypeError, ValueError):
        raise HTTPException(404, 'Documento non trovato') from None
    if expires < int(time.time()):
        raise HTTPException(410, 'Link documento scaduto')
    payload = f'{key}|{expires}|{download}'.encode('utf-8')
    expected = hmac.new(_local_secret(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(sig or '')):
        raise HTTPException(404, 'Documento non trovato')

    storage = LocalObjectStorage()
    path = storage._path(key)
    if not path.is_file():
        raise HTTPException(404, 'Documento non trovato')

    suffix = path.suffix.lower()
    content_type = {'.png': 'image/png', '.jpg': 'image/jpeg', '.pdf': 'application/pdf'}.get(suffix)
    if not content_type:
        raise HTTPException(404, 'Documento non trovato')
    disposition = 'attachment' if download else 'inline'
    return FileResponse(
        path,
        media_type=content_type,
        filename=path.name if download else None,
        headers={
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
            'Content-Disposition': f'{disposition}; filename="{path.name}"',
        },
    )


def get_storage():
    selected = backend()
    if selected == 'local':
        return LocalObjectStorage()
    if selected == 's3':
        return ObjectStorage()
    raise unavailable()


if __name__ == '__main__':
    from ..core.config import load_local_env
    load_local_env()
    get_storage().verify_configuration()
    print('Archivio POD configurato e verificato:', backend())
