import datetime
from urllib.parse import quote

import boto3
from botocore.signers import CloudFrontSigner
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.core.config import settings

# Global cache for performance
_CACHED_PRIVATE_KEY = None
_CACHED_S3_CLIENT = None


def rsa_signer(message):
    global _CACHED_PRIVATE_KEY

    if _CACHED_PRIVATE_KEY is None:
        private_key_str = settings.CLOUDFRONT_PRIVATE_KEY
        if not private_key_str:
            return None

        # Replace literal '\\n' with actual newlines if present in env var
        private_key_str = private_key_str.replace("\\n", "\n")

        try:
            _CACHED_PRIVATE_KEY = serialization.load_pem_private_key(
                private_key_str.encode("utf-8"),
                password=None,
                backend=default_backend(),
            )
        except Exception as e:
            print(f"Failed to load CloudFront private key: {e}")
            return None

    return _CACHED_PRIVATE_KEY.sign(message, padding.PKCS1v15(), hashes.SHA1())


def get_cloudfront_signed_url(s3_key: str, expires_in_seconds: int = 3600) -> str:
    """
    Generates a CloudFront signed URL for a given S3 object key.
    If CloudFront is not configured, falls back to S3 presigned URL (private) or public URL.
    """
    # If the key is already a full URL, return it
    if s3_key.startswith("http"):
        return s3_key

    domain = settings.CLOUDFRONT_DOMAIN
    key_pair_id = settings.CLOUDFRONT_KEY_PAIR_ID
    bucket_name = settings.S3_BUCKET_NAME
    aws_region = settings.AWS_REGION or "ap-south-1"

    # 1. Try CloudFront
    if domain and key_pair_id:
        # Ensure domain has protocol
        if not domain.startswith("http"):
            domain = f"https://{domain}"

        # Encode the S3 key
        encoded_key = quote(s3_key, safe="/")
        url = f"{domain}/{encoded_key}"
        expire_date = datetime.datetime.utcnow() + datetime.timedelta(
            seconds=expires_in_seconds
        )

        try:
            signer = CloudFrontSigner(key_pair_id, rsa_signer)
            return signer.generate_presigned_url(url, date_less_than=expire_date)
        except Exception as e:
            # Fallback if signing fails
            print(f"CloudFront signing failed: {e}")

    # 2. Fallback to Direct S3
    if bucket_name:
        global _CACHED_S3_CLIENT

        # Check if we have credentials for presigned URL
        aws_access_key = settings.AWS_ACCESS_KEY_ID
        aws_secret_key = settings.AWS_SECRET_ACCESS_KEY

        if aws_access_key and aws_secret_key:
            try:
                if _CACHED_S3_CLIENT is None:
                    _CACHED_S3_CLIENT = boto3.client(
                        "s3",
                        aws_access_key_id=aws_access_key,
                        aws_secret_access_key=aws_secret_key,
                        region_name=aws_region,
                    )
                return _CACHED_S3_CLIENT.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket_name, "Key": s3_key},
                    ExpiresIn=expires_in_seconds,
                )
            except Exception as e:
                print(f"S3 presigning failed: {e}")

        # 3. Public URL Fallback
        return f"https://{bucket_name}.s3.{aws_region}.amazonaws.com/{s3_key}"

    # 4. Give up, return key
    return s3_key
