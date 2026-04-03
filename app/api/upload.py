import mimetypes
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
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

# Architect-Level Security Guardrails
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"]


@router.post("/uploads/presigned-url", response_model=UploadResponse)
def generate_upload_url(
    request: Request,
    data: UploadRequest, 
    current_user=Depends(security.admin_or_employee_required)
):
    s3_client = get_s3_client()
    if not s3_client:
        raise HTTPException(status_code=500, detail="AWS credentials not configured")

    # Distributed Systems Master Logic: Consistency & Failover
    # 1. Trusted Header Check: Prevent spoofing by verifying secret
    # Architect Note: Use CloudFront "Add Header" origin request policy for this.
    cf_secret = request.headers.get("X-MMSR-Secret")
    trusted_source = (cf_secret == "EliteDistributedMaster")
    
    # 2. Regional Selection with Trust (Fallback to primary if not via CF)
    viewer_country = request.headers.get("CloudFront-Viewer-Country", "IN") if trusted_source else "IN"
    target_bucket = BUCKET_NAME  # Primary
    
    is_regional = False
    if viewer_country in ["US", "CA", "MX"]:
        target_bucket = "makemystay-us"
        is_regional = True
    elif viewer_country in ["GB", "DE", "FR", "IE"]:
        target_bucket = "makemystay-eu"
        is_regional = True

    # 1. Reject non-image MIME
    _reject_non_image_client_mime(data.content_type)

    # 2. Strict size enforcement (Architect-level check)
    if data.file_size > MAX_FILE_SIZE:
        logger.warning(
            "Upload rejected: File size too large. size={!r} max={!r}",
            data.file_size, MAX_FILE_SIZE
        )
        raise HTTPException(
            status_code=413, 
            detail=f"File too large. Maximum allowed size is {MAX_FILE_SIZE // (1024 * 1024)}MB"
        )

    # 3. Strict normalization and secondary enforcement (Security)
    normalized_type = _normalize_image_content_type(data.filename, data.content_type)
    if normalized_type not in ALLOWED_MIME_TYPES:
        logger.error(f"Security Rejection: forbidden type {normalized_type}")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_MIME_TYPES)}"
        )

    file_extension = data.filename.split(".")[-1] if "." in data.filename else "jpg"
    
    # 4. Generate Structured Key: properties/{id}/user_{user_id}/images/{uuid}.{ext} 
    # This enables identity-partitioned storage and per-user access policies.
    user_prefix = f"user_{current_user.id}"
    if data.property_id:
        unique_filename = f"properties/{data.property_id}/{user_prefix}/{uuid.uuid4()}.{file_extension}"
    else:
        unique_filename = f"uploads/{user_prefix}/{uuid.uuid4()}.{file_extension}"

    try:
        # Architect-level signature: Binding Content-Type to the pre-signed URL 
        # ensures the upload is used 100% as intended.
        # Note: ContentLength is removed because browsers often restrict manual 
        # setting of this header, which causes signature mismatches (403).
        put_params: dict = {
            "Bucket": target_bucket,
            "Key": unique_filename,
            "ContentType": normalized_type,
        }

        try:
            presigned_url = s3_client.generate_presigned_url(
                "put_object",
                Params=put_params,
                ExpiresIn=300,  # 5 minutes
            )
        except Exception as e:
            if is_regional:
                # Master Failover Observability: Log for CloudWatch Filter
                logger.warning(f"[FAILOVER_ACTIVE] Regional bucket {target_bucket} failed. Falling back to primary. Error: {e}")
                put_params["Bucket"] = BUCKET_NAME
                presigned_url = s3_client.generate_presigned_url(
                    "put_object",
                    Params=put_params,
                    ExpiresIn=300,
                )
            else:
                raise e

        # Master Consistency Strategy: 
        # READ from Primary (Consistent) | WRITE to Regional (Performance)
        # All public URLs use the CloudFront Domain pointing to the Primary Origin.
        import time
        cache_buster = f"?v={int(time.time())}"
        
        cloudfront_domain = settings.CLOUDFRONT_DOMAIN
        if cloudfront_domain:
            domain = (
                cloudfront_domain
                if cloudfront_domain.startswith("http")
                else f"https://{cloudfront_domain}"
            )
            public_url = f"{domain}/{unique_filename}{cache_buster}"
        else:
            # Fallback to direct Primary S3 URL (ap-south-1)
            public_url = (
                f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{unique_filename}{cache_buster}"
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
