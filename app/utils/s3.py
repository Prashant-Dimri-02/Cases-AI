# app/utils/s3.py
# optional - placeholder for uploading file bytes to S3
import boto3
from app.core.config import settings

def upload_bytes_to_s3(key: str, data: bytes):
    if not settings.S3_BUCKET:
        raise RuntimeError("S3 not configured")
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
    )
    s3.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data)
    return key
