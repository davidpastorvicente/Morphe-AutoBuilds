"""R2 / S3 storage helpers for uploading APK artifacts."""

import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.client import Config

from src import ACCESS_KEY_ID, BUCKET_NAME, ENDPOINT_URL, SECRET_ACCESS_KEY


def delete_old_files(
    s3_client, bucket: str, prefix: str, threshold_minutes: int = 60
) -> None:
    """Remove objects older than *threshold_minutes* under *prefix*."""
    objects = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

    for obj in objects.get("Contents", []):
        age = datetime.now(timezone.utc) - obj["LastModified"]
        if age > timedelta(minutes=threshold_minutes):
            s3_client.delete_object(Bucket=bucket, Key=obj["Key"])
            logging.info("Deleted old file: %s", obj["Key"])


def upload(file_path: str, key: str) -> None:
    """Upload *file_path* to R2/S3 at *key*, removing stale siblings first."""
    s3_client = boto3.client(
        "s3",
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=ACCESS_KEY_ID,
        aws_secret_access_key=SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
    )

    delete_old_files(s3_client, BUCKET_NAME, key.rsplit("/", 1)[0])

    with open(file_path, "rb") as fh:
        s3_client.upload_fileobj(fh, BUCKET_NAME, key)

    logging.info("Upload success: %s", key)
