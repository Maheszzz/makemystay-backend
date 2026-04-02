import mimetypes
import uuid

import boto3
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from app.core import security
from app.core.config import settings
from app.schemas.upload import UploadRequest, UploadResponse

router = APIRouter()


def _normalize_image_content_type(filename: str, content_type: str) -> str:
    """Infer MIME from filename when the browser omits or misreports file.type (common for WhatsApp exports)."""
    ct = (content_type or "").strip().lower()
    if ct == "image/jpg":
        ct = "image/jpeg"
    if ct.startswith("image/"):
        return ct
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    guessed, _ = mimetypes.guess_type(f"file.{ext}" if ext else filename)
    if guessed and guessed.startswith("image/"):
        return guessed.lower()
    logger.warning(
        "MIME fallback to image/jpeg (could not infer from client or filename): filename={!r} client_type={!r}",
        filename,
        content_type,
    )
    return "image/jpeg"


def _reject_non_image_client_mime(content_type: str) -> None:
    """Allow empty / octet-stream (browsers) / image/*. Block obvious non-images before signing."""
    ct = (content_type or "").strip().lower()
    if not ct or ct == "application/octet-stream":
        return
    if ct.startswith("image/"):
        return
    raise HTTPException(
        status_code=400,
        detail="Only image files are allowed",
    )


# AWS Configuration
AWS_ACCESS_KEY_ID = settings.AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = settings.AWS_SECRET_ACCESS_KEY
AWS_REGION = settings.AWS_REGION or "ap-south-1"
BUCKET_NAME = settings.S3_BUCKET_NAME


def get_s3_client():
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.warning("AWS credentials not found. S3 uploads will fail.")
        return None

    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


@router.post("/uploads/presigned-url", response_model=UploadResponse)
def generate_upload_url(
    data: UploadRequest, current_admin=Depends(security.admin_required)
):
    s3_client = get_s3_client()
    if not s3_client:
        raise HTTPException(status_code=500, detail="AWS credentials not configured")

    if not BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")

    _reject_non_image_client_mime(data.content_type)

    normalized_type = _normalize_image_content_type(data.filename, data.content_type)
    if not normalized_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    file_extension = data.filename.split(".")[-1] if "." in data.filename else "jpg"
    unique_filename = f"uploads/{uuid.uuid4()}.{file_extension}"

    try:
        put_params: dict = {
            "Bucket": BUCKET_NAME,
            "Key": unique_filename,
            "ContentType": normalized_type,
        }
        if data.file_size is not None:
            put_params["ContentLength"] = data.file_size

        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params=put_params,
            ExpiresIn=300,  # 5 minutes
        )

        # Public URL uses the same object key; when CLOUDFRONT_DOMAIN is set, that origin serves this path too.

        # We pass a long expiry since these URLs will be stored in the DB,
        # but if CloudFront isn't configured, it falls back to a public S3 URL anyway.
        # Alternatively, for public assets, we just want the public URL base.
        # Since uploads are public, let's just construct the direct public URL
        # or use the CloudFront domain if available.
        cloudfront_domain = settings.CLOUDFRONT_DOMAIN
        if cloudfront_domain:
            domain = (
                cloudfront_domain
                if cloudfront_domain.startswith("http")
                else f"https://{cloudfront_domain}"
            )
            public_url = f"{domain}/{unique_filename}"
        else:
            public_url = (
                f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{unique_filename}"
            )

        logger.info(
            "Presigned S3 PUT URL issued: filename={!r} content_type={!r} file_key={!r} file_size={!r}",
            data.filename,
            normalized_type,
            unique_filename,
            data.file_size,
        )

        return {
            "upload_url": presigned_url,
            "file_key": unique_filename,
            "public_url": public_url,
            "content_type": normalized_type,
        }
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Could not generate upload URL")
