from io import BytesIO

from minio import Minio
from minio.error import S3Error

from .config import settings

_client: Minio | None = None


def client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_secure,
        )
        # Idempotent bucket ensure (handy when running outside docker-compose).
        try:
            if not _client.bucket_exists(settings.s3_bucket_raw):
                _client.make_bucket(settings.s3_bucket_raw)
        except S3Error:
            # Bucket may exist with a different policy; that's fine for v0.
            pass
    return _client


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload bytes and return the s3:// URI."""
    client().put_object(
        settings.s3_bucket_raw,
        key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"s3://{settings.s3_bucket_raw}/{key}"


def get_bytes(key: str) -> bytes:
    resp = client().get_object(settings.s3_bucket_raw, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()
