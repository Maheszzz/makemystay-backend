"""Shared boto3 S3 client for uploads and optional object checks."""

import boto3
from loguru import logger
from botocore.config import Config

from app.core.config import settings


def get_s3_client():
    """Return a configured S3 client. Falls back to IAM Instance Profile if keys are missing."""
    key_id = settings.AWS_ACCESS_KEY_ID
    secret = settings.AWS_SECRET_ACCESS_KEY
    region = settings.AWS_REGION or "ap-south-1"
    
    # SigV4 is mandatory for newer regions like Mumbai (ap-south-1).
    s3_config = Config(
        signature_version="s3v4",
        retries={"max_attempts": 3, "mode": "standard"}
    )

    if not key_id or not secret:
        logger.info("Initializing S3 client using Identity-based (IAM) credentials.")
        return boto3.client(
            "s3",
            region_name=region,
            endpoint_url=f"https://s3.{region}.amazonaws.com",
            config=s3_config
        )

    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=s3_config,
    )
