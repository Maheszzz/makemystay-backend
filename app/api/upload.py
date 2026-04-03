import mimetypes
import uuid

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from app.core import security
from app.core.config import settings
from app.schemas.upload import UploadRequest, UploadResponse
from app.utils.s3_client import get_s3_client

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


AWS_REGION = settings.AWS_REGION or "ap-south-1"
BUCKET_NAME = settings.S3_BUCKET_NAME

# Security Constraints
ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"]


@router.post("/uploads/presigned-url", response_model=UploadResponse)
def generate_upload_url(
    data: UploadRequest, current_admin=Depends(security.admin_required)
):
    s3_client = get_s3_client()
    if not s3_client:
        raise HTTPException(status_code=500, detail="AWS credentials not configured")

    if not BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")

    # 1. Initial reject based on client-provided MIME
    _reject_non_image_client_mime(data.content_type)

    # 2. Strict normalization and secondary enforcement (Security)
    normalized_type = _normalize_image_content_type(data.filename, data.content_type)
    if normalized_type not in ALLOWED_MIME_TYPES:
        logger.error(f"Security Rejection: forbidden type {normalized_type}")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_MIME_TYPES)}"
        )

    file_extension = data.filename.split(".")[-1] if "." in data.filename else "jpg"
    
    # 3. Generate Structured Key: properties/{id}/images/{uuid}.{ext} 
    # Fallback to general uploads/ if no property_id is provided.
    if data.property_id:
        unique_filename = f"properties/{data.property_id}/images/{uuid.uuid4()}.{file_extension}"
    else:
        unique_filename = f"uploads/{uuid.uuid4()}.{file_extension}"

    try:
        # Presign with Bucket + Key only so SigV4 signs `host` (see X-Amz-SignedHeaders).
        # Binding ContentType or ContentLength into the URL requires the browser PUT to match
        # those headers exactly; fetch() often breaks that (Content-Length vs chunked body,
        # MIME quirks). We already validate MIME below; the client still sends Content-Type
        # on PUT so S3 stores correct object metadata.
        put_params: dict = {
            "Bucket": BUCKET_NAME,
            "Key": unique_filename,
        }

        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params=put_params,
            ExpiresIn=300,  # 5 minutes
        )

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
            "S3 Upload Signed: key={!r} type={!r} size={!r} url_start={!r}",
            unique_filename,
            normalized_type,
            data.file_size,
            presigned_url[:60] + "...",
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
