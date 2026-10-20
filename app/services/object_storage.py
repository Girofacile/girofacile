"""Private delivery-evidence storage. No client or network access at import time.

Production uses S3-compatible object storage. Development may use a local
filesystem archive (OBJECT_STORAGE_BACKEND=local) to test signatures, photos
and POD PDFs without external services.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class StorageUnavailable(HTTPException):
    """Sanitized failure registered by the application's existing error monitor."""


def enabled():
    return os.getenv('OBJECT_STORAGE_ENABLED', 'false').lower() in ('true', '1', 'yes')


def backend():
    return (os.getenv('OBJECT_STORAGE_BACKEND', 's3') or 's3').strip().lower()


def _is_development():
    return os.getenv('APP_ENV', 'development').strip().lower() in ('development', 'dev', 'test', 'testing')


def unavailable():
    # Never log the provider exception: it may contain credentials or signed URLs.
    logger.error('POD object storage unavailable; check configuration and provider health')
    return StorageUnavailable(503, 'Archivio POD non disponibile. Firma e foto non salvate: conserva questa schermata e riprova.')


def _configuration_values():
    values = {name: os.getenv('OBJECT_STORAGE_' + name, '').strip() for name in
              ('ENDPOINT', 'REGION', 'BUCKET', 'ACCESS_KEY', 'SECRET_KEY')}
    try:
        seconds = int(os.getenv('OBJECT_STORAGE_SIGNED_URL_SECONDS', '900'))
        if not enabled() or not all(values.values()) or not 60 <= seconds <= 900:
            return None
        from urllib.parse import urlsplit
        endpoint = urlsplit(values['ENDPOINT'])
        if endpoint.scheme != 'https' or not endpoint.netloc or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            return None
    except (TypeError, ValueError):
        return None
    return values, seconds


def local_root():
    raw = os.getenv('OBJECT_STORAGE_LOCAL_PATH', '').strip()
    root = Path(raw).expanduser() if raw else Path('data') / 'pod_storage'
    if not root.is_absolute():
        root = Path(__file__).resolve().parent.parent.parent / root
    return root.resolve()


def _local_configuration_values():
    """Local archive: development only, never in production."""
    secret = os.getenv('OBJECT_STORAGE_LOCAL_SECRET', '').strip() or os.getenv('APP_SECRET', '').strip()
    try:
        seconds = int(os.getenv('OBJECT_STORAGE_SIGNED_URL_SECONDS', '900'))
    except (TypeError, ValueError):
        return None
    if not enabled() or not _is_development() or not secret or not 60 <= seconds <= 900:
        return None
    return secret.encode('utf-8'), seconds


def configured():
    """True only when optional POD generation has a complete local configuration."""
    if backend() == 'local':
        return _local_configuration_values() is not None
    return backend() == 's3' and _configuration_values() is not None


def configuration():
    result = _configuration_values()
    if result is None:
        raise unavailable() from None
    return result


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


class ObjectStorage:
    def __init__(self):
        values, self.seconds = configuration()
        try:
            import boto3
            from botocore.config import Config
            self.bucket = values['BUCKET']
            self._private_checked = False
            self.client = boto3.client('s3', endpoint_url=values['ENDPOINT'],
                region_name=values['REGION'], aws_access_key_id=values['ACCESS_KEY'],
                aws_secret_access_key=values['SECRET_KEY'],
                config=Config(signature_version='s3v4', s3={'addressing_style': 'path'},
                              connect_timeout=5, read_timeout=20, retries={'max_attempts': 2}))
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
            self.client.put_object(Bucket=self.bucket, Key=key, Body=raw,
                ContentType=content_type, ACL='private',
                Metadata={'sha256': hashlib.sha256(raw).hexdigest()})
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
            return self.client.generate_presigned_url('get_object', Params={
                'Bucket': self.bucket, 'Key': key, 'ResponseContentType': content_type,
                'ResponseContentDisposition': ('attachment' if download else 'inline') + '; filename="' + key.rsplit('/', 1)[1] + '"'},
                ExpiresIn=self.seconds)
        except Exception:
            raise unavailable() from None

    def delete(self, key):
        # Callers validate scope; this extra guard excludes arbitrary bucket objects.
        if not EVIDENCE_KEY_RE.fullmatch(key):
            raise ValueError('Invalid evidence key')
        self.client.delete_object(Bucket=self.bucket, Key=key)


EVIDENCE_KEY_RE = re.compile(r'companies/\d+/routes/\d+/deliveries/\d+/(signature|delivery_photo|pod)-[a-f0-9]{32}\.(png|jpg|pdf)')


def _generic_key(key):
    if not isinstance(key, str) or not EVIDENCE_KEY_RE.fullmatch(key):
        raise HTTPException(404, 'Documento non trovato')
    return key


def _local_signature(secret, key, expires, download):
    return hmac.new(secret, f'{key}|{expires}|{download}'.encode('utf-8'), hashlib.sha256).hexdigest()


class LocalObjectStorage:
    """Development-only private filesystem archive.

    Files stay outside the database and open through short-lived HMAC links
    served by GiroFacile itself, like the S3 temporary links.
    """

    def __init__(self):
        values = _local_configuration_values()
        if values is None:
            raise unavailable()
        self._secret, self.seconds = values
        self.root = local_root()

    def verify_configuration(self):
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / '.write-test'
            probe.write_bytes(b'ok')
            probe.unlink()
        except Exception:
            raise unavailable() from None

    def _path(self, key):
        path = (self.root / _generic_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise HTTPException(404, 'Documento non trovato')
        return path

    def upload(self, key, raw, content_type):
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + '.part' + uuid4().hex[:8])
            tmp.write_bytes(raw)
            tmp.replace(path)
        except Exception:
            raise unavailable() from None

    def read(self, key):
        path = self._path(key)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raise HTTPException(404, 'Documento non trovato') from None
        except Exception:
            raise unavailable() from None
        if len(raw) > 12_000_000:
            raise unavailable()
        return raw

    def signed_url(self, key, content_type, download=False):
        _generic_key(key)
        expires, dl = int(time.time()) + self.seconds, 1 if download else 0
        return '/api/pod-local?' + urlencode({'key': key, 'exp': expires, 'dl': dl,
                                             'sig': _local_signature(self._secret, key, expires, dl)})

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)


def serve_local_object(key, exp, dl, sig):
    """Serve a file of the local archive through its expiring signed link."""
    values = _local_configuration_values()
    if backend() != 'local' or values is None:
        raise HTTPException(404, 'Documento non trovato')
    _generic_key(key)
    download = 1 if dl else 0
    if not hmac.compare_digest(_local_signature(values[0], key, exp, download), str(sig or '')):
        raise HTTPException(404, 'Documento non trovato')
    if exp < int(time.time()):
        raise HTTPException(410, 'Link documento scaduto')
    path = LocalObjectStorage()._path(key)
    if not path.is_file():
        raise HTTPException(404, 'Documento non trovato')
    from fastapi.responses import FileResponse
    content_type = {'.png': 'image/png', '.jpg': 'image/jpeg', '.pdf': 'application/pdf'}[path.suffix]
    disposition = 'attachment' if download else 'inline'
    return FileResponse(path, media_type=content_type, headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Content-Disposition': f'{disposition}; filename="{path.name}"'})


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
