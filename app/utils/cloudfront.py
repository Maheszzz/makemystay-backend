import os
import datetime
from urllib.parse import quote
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from botocore.signers import CloudFrontSigner

def rsa_signer(message):
    private_key_str = os.getenv('CLOUDFRONT_PRIVATE_KEY')
    if not private_key_str:
        return None
        
    # Replace literal '\\n' with actual newlines if present in env var
    private_key_str = private_key_str.replace('\\n', '\n')
    
    private_key = serialization.load_pem_private_key(
        private_key_str.encode('utf-8'),
        password=None,
        backend=default_backend()
    )
    return private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())

def get_cloudfront_signed_url(s3_key: str, expires_in_seconds: int = 3600) -> str:
    """
    Generates a CloudFront signed URL for a given S3 object key.
    """
    domain = os.getenv('CLOUDFRONT_DOMAIN')
    key_pair_id = os.getenv('CLOUDFRONT_KEY_PAIR_ID')

    if not domain or not key_pair_id:
        # Fallback to direct S3 URL or placeholder if config is missing
        bucket = os.getenv('S3_BUCKET_NAME')
        region = os.getenv('AWS_REGION')
        if bucket and region:
             return f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"
        return s3_key

    # Ensure domain has protocol
    if not domain.startswith('http'):
        domain = f"https://{domain}"

    # Encode the S3 key to handle spaces and special characters
    # safe='/' ensures slashes are NOT encoded, preserving the directory structure
    encoded_key = quote(s3_key, safe='/')
    
    url = f"{domain}/{encoded_key}"
    expire_date = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in_seconds)

    signer = CloudFrontSigner(key_pair_id, rsa_signer)
    return signer.generate_presigned_url(url, date_less_than=expire_date)
