from fastapi import APIRouter, HTTPException, Depends
from app.schemas.upload import UploadRequest, UploadResponse
import boto3
import uuid
import os
from loguru import logger

router = APIRouter()

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

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
def generate_upload_url(data: UploadRequest):
    s3_client = get_s3_client()
    if not s3_client:
        raise HTTPException(status_code=500, detail="AWS credentials not configured")
    
    if not BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")

    # Validate file type (basic)
    if not data.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    file_extension = data.filename.split(".")[-1] if "." in data.filename else "jpg"
    unique_filename = f"uploads/{uuid.uuid4()}.{file_extension}"

    try:
        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": unique_filename,
                "ContentType": data.content_type,
                # "ACL": "private" # Bucket is private by default, avoiding explicit ACL can be safer depending on bucket settings
            },
            ExpiresIn=300,  # 5 minutes
        )

        return {
            "upload_url": presigned_url,
            "file_key": unique_filename
        }
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Could not generate upload URL")
