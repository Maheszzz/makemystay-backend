import mimetypes
import uuid
from typing import Optional
from loguru import logger
import time

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from app.core import security
from app.core.config import settings
from app.schemas.upload import UploadRequest, UploadResponse
from app.utils.s3_client import get_s3_client

router = APIRouter()

def _normalize_image_content_type(filename: str, content_type: str) -> str:
    """Infer MIME from filename when the browser omits or misreports file.type."""
    ct = (content_type or "").strip().lower()
    if ct == "image/jpg":
        ct = "image/jpeg"
    if ct.startswith("image/"):
        return ct
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    guessed, _ = mimetypes.guess_type(f"file.{ext}" if ext else filename)
    if guessed and guessed.startswith("image/"):
        return guessed.lower()
    return "image/jpeg"

@router.get("/uploads/test")
async def test_upload_router():
    """Verify that the router is correctly registered and reachable."""
    return {"status": "router_active"}

@router.post("/uploads/binary")
@router.post("/upload/image")
@router.post("/upload/document")
@router.post("/upload/video-thumbnail")
@router.post("/uploads/image")
@router.post("/uploads/document")
@router.post("/uploads/video-thumbnail")
async def proxy_upload_to_s3(
    request: Request,
    property_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user=Depends(security.admin_or_employee_required)
):
    """
    Absolute Ingestion Fix & Sprint 4 Upload System: Proxy browser upload through backend to eliminate S3 signature/CORS issues.
    Supports images, PDFs, and video thumbnails.
    """
    print(f"DEBUG: ALL HEADERS RECEIVED: {dict(request.headers)}")
    logger.info(f"PROXY HIT | auth={request.headers.get('authorization', 'MISSING')[:15]}... | type={request.headers.get('content-type')}")
    logger.info(f"PROXY START | file={file.filename} property_id={property_id} user={current_user.id}")
    
    s3_client = get_s3_client()
    if not s3_client:
        logger.error("AWS S3 Client Initialization Failed")
        raise HTTPException(status_code=500, detail="AWS credentials not configured")

    BUCKET_NAME = settings.S3_BUCKET_NAME
    AWS_REGION = settings.AWS_REGION or "ap-south-1"
    
    if not BUCKET_NAME:
        logger.error("S3_BUCKET_NAME missing in env")
        raise HTTPException(status_code=500, detail="S3 bucket not configured")

    # 1. MIME Normalization
    def get_normalized_mime(name: str, ctype: str) -> str:
        c = (ctype or "").strip().lower()
        if c == "image/jpg": c = "image/jpeg"
        # Allowed types
        if c in ["image/jpeg", "image/png", "image/webp", "application/pdf", "image/gif", "image/svg+xml"]:
            return c
        # Fallback to extension
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext in ["jpg", "jpeg"]: return "image/jpeg"
        if ext == "png": return "image/png"
        if ext == "webp": return "image/webp"
        if ext == "pdf": return "application/pdf"
        return "application/octet-stream" if ext in ["pdf", "doc", "docx"] else "image/jpeg"

    normalized_type = get_normalized_mime(file.filename, file.content_type)

    # 2. Key Generation
    user_prefix = f"user_{current_user.id}"
    file_extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    
    if property_id:
        unique_filename = f"properties/{property_id}/{user_prefix}/{uuid.uuid4()}.{file_extension}"
    else:
        unique_filename = f"uploads/{user_prefix}/{uuid.uuid4()}.{file_extension}"

    try:
        # 3. Hardened Ingestion: Read into memory and use put_object
        logger.info(f"READING FILE | {file.filename}")
        contents = await file.read()
        logger.info(f"READ COMPLETE | bytes={len(contents)}")

        if not contents:
            logger.error("Empty file received from client")
            raise Exception("Empty file received")
        
        logger.info(f"S3 PUT START | key={unique_filename}")
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=unique_filename,
            Body=contents,
            ContentType=normalized_type
        )
        logger.info("S3 PUT SUCCESS")

        cache_buster = f"?v={int(time.time())}"
        
        # 4. Construct Public URL
        cloudfront_domain = settings.CLOUDFRONT_DOMAIN
        if cloudfront_domain:
            domain = cloudfront_domain if cloudfront_domain.startswith("http") else f"https://{cloudfront_domain}"
            public_url = f"{domain}/{unique_filename}{cache_buster}"
        else:
            public_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{unique_filename}{cache_buster}"

        logger.info(f"Successful Proxy Upload: {unique_filename} via user {current_user.id}")
        
        return {
            "url": public_url,
            "filename": file.filename,
            "size": len(contents),
            "mime_type": normalized_type,
            # Backwards-compatible aliases
            "file_key": unique_filename,
            "public_url": public_url,
            "content_type": normalized_type,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"Proxy Upload Failed: {e}")
        raise HTTPException(status_code=500, detail=f"S3 ingestion failed: {str(e)}")


@router.post("/uploads/presigned-url", response_model=UploadResponse)
def generate_upload_url(
    request: Request,
    data: UploadRequest, 
    current_user=Depends(security.admin_or_employee_required)
):
    s3_client = get_s3_client()
    if not s3_client:
        raise HTTPException(status_code=500, detail="AWS credentials not configured")

    BUCKET_NAME = settings.S3_BUCKET_NAME
    # Regional Failover Logic
    target_bucket = BUCKET_NAME
    
    # Simple whitelist for now
    if data.file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    normalized_type = _normalize_image_content_type(data.filename, data.content_type)
    file_extension = data.filename.split(".")[-1] if "." in data.filename else "jpg"
    user_prefix = f"user_{current_user.id}"
    
    if data.property_id:
        unique_filename = f"properties/{data.property_id}/{user_prefix}/{uuid.uuid4()}.{file_extension}"
    else:
        unique_filename = f"uploads/{user_prefix}/{uuid.uuid4()}.{file_extension}"

    try:
        conditions = [
            ["content-length-range", 0, 5 * 1024 * 1024],
            {"Content-Type": normalized_type},
        ]
        
        post_response = s3_client.generate_presigned_post(
            Bucket=target_bucket,
            Key=unique_filename,
            Fields={"Content-Type": normalized_type},
            Conditions=conditions,
            ExpiresIn=300,
        )
        
        cache_buster = f"?v={int(time.time())}"
        cloudfront_domain = settings.CLOUDFRONT_DOMAIN
        if cloudfront_domain:
            domain = cloudfront_domain if cloudfront_domain.startswith("http") else f"https://{cloudfront_domain}"
            public_url = f"{domain}/{unique_filename}{cache_buster}"
        else:
            public_url = f"https://{BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{unique_filename}{cache_buster}"

        return {
            "upload_url": post_response["url"],
            "fields": post_response["fields"],
            "file_key": unique_filename,
            "public_url": public_url,
            "content_type": normalized_type,
        }
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Could not generate upload URL")
