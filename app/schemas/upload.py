from pydantic import BaseModel, Field
from typing import Optional, Dict

# Keep in sync with makemystay-admin `MAX_IMAGE_UPLOAD_BYTES` (presigned PUT + UI).
MAX_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024


class UploadRequest(BaseModel):
    filename: str
    content_type: str
    # Optional context for structured S3 key generation
    property_id: Optional[int] = Field(default=None, ge=1)
    # Required: enforced server-side before presign (S3 presign does not bind Content-Length).
    file_size: int = Field(..., ge=1, le=MAX_IMAGE_UPLOAD_BYTES)


class UploadResponse(BaseModel):
    upload_url: str
    file_key: str
    public_url: str
    # MIME to send on PUT (S3 object metadata); presigned URL no longer binds it in the signature.
    content_type: str
    # Fields required for S3 Presigned POST uploads
    fields: Optional[Dict[str, str]] = None
