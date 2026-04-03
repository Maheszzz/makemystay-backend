"""Shared boto3 S3 client for uploads and optional object checks."""

import boto3
from loguru import logger

from app.core.config import settings


def get_s3_client():
    """Return a configured S3 client, or None if credentials are missing."""
    key_id = settings.AWS_ACCESS_KEY_ID
    secret = settings.AWS_SECRET_ACCESS_KEY
    if not key_id or not secret:
        logger.warning("AWS credentials not found. S3 operations will fail.")
        return None

    region = settings.AWS_REGION or "ap-south-1"
    from botocore.config import Config
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        config=Config(signature_version="s3v4"),
    )
