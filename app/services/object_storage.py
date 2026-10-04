"""Private S3 evidence storage. No client or network access at import time."""
import hashlib
import ipaddress
import json
import logging
import os
import re
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class StorageUnavailable(HTTPException):
    """Sanitized failure registered by the application's existing error monitor."""


def enabled():
    return os.getenv('OBJECT_STORAGE_ENABLED', 'false').lower() in ('true', '1', 'yes')


def unavailable():
    # Never log the provider exception: it may contain credentials or signed URLs.
    logger.error('POD object storage unavailable; check configuration and provider health')
    return StorageUnavailable(503, 'Archivio POD non disponibile. Firma e foto non salvate: conserva questa schermata e riprova.')


def _is_local_development_host(hostname):
    host = (hostname or '').strip().lower()
    if host in ('localhost', 'minio', 'host.docker.internal'):
        return True
    try:
        address = ipaddress.ip_address(host)
        return bool(address.is_loopback or address.is_private or address.is_link_local)
    except ValueError:
        return host.endswith('.local')


def _validate_endpoint(value, *, allow_local_http):
    endpoint = urlsplit(value)
    if (
        not endpoint.netloc
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or endpoint.path not in ('', '/')
    ):
        raise ValueError()
    if endpoint.scheme == 'https':
        return value.rstrip('/')
    if endpoint.scheme == 'http' and allow_local_http and _is_local_development_host(endpoint.hostname):
        return value.rstrip('/')
    raise ValueError()


def configuration():
    values = {name: os.getenv('OBJECT_STORAGE_' + name, '').strip() for name in
              ('ENDPOINT', 'REGION', 'BUCKET', 'ACCESS_KEY', 'SECRET_KEY')}
    try:
        seconds = int(os.getenv('OBJECT_STORAGE_SIGNED_URL_SECONDS', '900'))
        app_env = os.getenv('APP_ENV', 'development').strip().lower()
        allow_local_http = app_env in ('development', 'dev', 'test', 'testing')
        if not enabled() or not all(values.values()) or not 60 <= seconds <= 900:
            raise ValueError()
        values['ENDPOINT'] = _validate_endpoint(values['ENDPOINT'], allow_local_http=allow_local_http)
        public_endpoint = os.getenv('OBJECT_STORAGE_PUBLIC_ENDPOINT', '').strip() or values['ENDPOINT']
        values['PUBLIC_ENDPOINT'] = _validate_endpoint(public_endpoint, allow_local_http=allow_local_http)
        values['LOCAL_DEVELOPMENT'] = (
            allow_local_http
            and urlsplit(values['ENDPOINT']).scheme == 'http'
            and _is_local_development_host(urlsplit(values['ENDPOINT']).hostname)
        )
    except ValueError:
        raise unavailable() from None
    return values, seconds


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
            self.local_development = bool(values.get('LOCAL_DEVELOPMENT'))
            client_config = Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'},
                connect_timeout=5,
                read_timeout=20,
                retries={'max_attempts': 2},
            )
            common = dict(
                region_name=values['REGION'],
                aws_access_key_id=values['ACCESS_KEY'],
                aws_secret_access_key=values['SECRET_KEY'],
                config=client_config,
            )
            self.client = boto3.client('s3', endpoint_url=values['ENDPOINT'], **common)
            self.presign_client = (
                self.client if values['PUBLIC_ENDPOINT'] == values['ENDPOINT']
                else boto3.client('s3', endpoint_url=values['PUBLIC_ENDPOINT'], **common)
            )
        except Exception:
            raise unavailable() from None

    def verify_configuration(self):
        """Refuse public buckets in production; local MinIO is checked for reachability."""
        try:
            if self.local_development:
                # Local MinIO is provisioned private by docker-compose. Some S3-compatible
                # development servers do not implement ACL APIs, so only verify the bucket.
                self.client.head_bucket(Bucket=self.bucket)
                self._private_checked = True
                return
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
            # Bucket privacy is verified separately. Omitting x-amz-acl also improves
            # compatibility with MinIO and S3 providers that disable object ACLs.
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
            return self.presign_client.generate_presigned_url('get_object', Params={
                'Bucket': self.bucket, 'Key': key, 'ResponseContentType': content_type,
                'ResponseContentDisposition': ('attachment' if download else 'inline') + '; filename="' + key.rsplit('/', 1)[1] + '"'},
                ExpiresIn=self.seconds)
        except Exception:
            raise unavailable() from None

    def delete(self, key):
        # Callers validate scope; this extra guard excludes arbitrary bucket objects.
        if not re.fullmatch(r'companies/\d+/routes/\d+/deliveries/\d+/(signature|delivery_photo|pod)-[a-f0-9]{32}\.(png|jpg|pdf)', key):
            raise ValueError('Invalid evidence key')
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_storage():
    return ObjectStorage()


if __name__ == '__main__':
    from ..core.config import load_local_env
    load_local_env()
    get_storage().verify_configuration()
    print('Archivio POD configurato e bucket privato verificato')
