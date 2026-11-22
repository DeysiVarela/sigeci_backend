import os
import uuid
import boto3
from botocore.config import Config
from django.conf import settings

s3 = boto3.client(
    "s3",
    endpoint_url            =settings.SUPABASE_S3_ENDPOINT,
    region_name             =settings.SUPABASE_S3_REGION,
    aws_access_key_id       =settings.SUPABASE_S3_ACCESS_KEY,
    aws_secret_access_key   =settings.SUPABASE_S3_SECRET_KEY,
    config                  =Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)

def generate_upload_url(folder: str, filename: str, content_type: str, expires_in: int = 300) -> dict:
    ext = os.path.splitext(filename)[1].lower()
    key = f"{folder}/{uuid.uuid4()}{ext}"

    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.SUPABASE_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )
    return {"url": url, "path": key, "content_type": content_type}


def generate_download_url(key: str, expires_in: int = 3600) -> str:
    if not key:
        return key
    if key.startswith("http://") or key.startswith("https://"):
        return key
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.SUPABASE_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )


def delete_file(key: str) -> bool:
    if not key:
        return False
    if key.startswith("http://") or key.startswith("https://"):
        bucket_prefix = f"/{settings.SUPABASE_BUCKET}/"
        if bucket_prefix in key:
            key = key.split(bucket_prefix, 1)[1].split("?", 1)[0]
        else:
            return False
    s3.delete_object(Bucket=settings.SUPABASE_BUCKET, Key=key)
    return True