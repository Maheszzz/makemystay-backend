"""
Property Media APIs (Sprint 3): Images, 11 PDF Documents, and Videos.
Includes CRM Lead capture before premium PDF download.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.rate_limit import limiter
from app.models.realty import PropertyImage
from app.models.realty_enterprise import PropertyDocument, PropertyVideo
from app.schemas.property_enterprise import (
    PropertyDocumentSchema,
    PropertyVideoSchema,
)

router = APIRouter()


# ==================== DOCUMENTS (SPRINT 3 & 9) ====================

@router.post("/properties/{property_id}/documents", response_model=PropertyDocumentSchema, status_code=201)
def add_property_document(
    property_id: int,
    data: PropertyDocumentSchema,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Add a PDF or sales kit document to a property (brochure, pricing, wap, floor_plan, etc.)."""
    doc = PropertyDocument(
        property_id=property_id,
        document_type=data.document_type,
        title=data.title,
        document_url=data.document_url,
        file_size=data.file_size,
        mime_type=data.mime_type or "application/pdf",
        created_by=str(current_user.id),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/properties/{property_id}/documents", response_model=List[PropertyDocumentSchema])
def list_property_documents(
    property_id: int,
    db: Session = Depends(get_mysql_db),
):
    """List all documents for a property."""
    return (
        db.query(PropertyDocument)
        .filter(PropertyDocument.property_id == property_id, PropertyDocument.is_deleted == False)
        .order_by(PropertyDocument.id.asc())
        .all()
    )


@router.post("/documents/{doc_id}/download")
@limiter.limit("10/minute")
def download_property_document_with_lead_capture(
    request: Request,
    doc_id: int,
    user_name: str = Query(..., description="User's full name"),
    user_phone: str = Query(..., description="User's phone number"),
    user_email: str = Query(..., description="User's email address"),
    user_company: Optional[str] = Query(None, description="Company name"),
    purpose: Optional[str] = Query(None, description="Purpose of download"),
    db: Session = Depends(get_mysql_db),
):
    """
    Sprint 9 Lead Capture: Before downloading a premium document, capture Name, Phone, Email, Company, Purpose.
    Automatically logs PropertyDownload and generates an assigned CRM Lead.
    Returns the secure document URL.
    """
    doc = db.query(PropertyDocument).filter(PropertyDocument.id == doc_id, PropertyDocument.is_deleted == False).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")


    return {
        "status": "success",
        "document_id": doc.id,
        "title": doc.title,
        "document_type": doc.document_type,
        "document_url": doc.document_url,
    }


@router.delete("/documents/{doc_id}", status_code=204)
def delete_property_document(
    doc_id: int,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Soft delete a property document."""
    doc = db.query(PropertyDocument).filter(PropertyDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.is_deleted = True
    doc.updated_by = str(current_user.id)
    db.commit()
    return None


# ==================== VIDEOS (SPRINT 3) ====================

@router.post("/properties/{property_id}/videos", response_model=PropertyVideoSchema, status_code=201)
def add_property_video(
    property_id: int,
    data: PropertyVideoSchema,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Add a YouTube walkthrough or Property Short video to a property."""
    vid = PropertyVideo(
        property_id=property_id,
        title=data.title,
        video_url=data.video_url,
        thumbnail_url=data.thumbnail_url,
        is_short=data.is_short,
        sort_order=data.sort_order,
        created_by=str(current_user.id),
    )
    db.add(vid)
    db.commit()
    db.refresh(vid)
    return vid


@router.get("/properties/{property_id}/videos", response_model=List[PropertyVideoSchema])
def list_property_videos(
    property_id: int,
    db: Session = Depends(get_mysql_db),
):
    """List all videos for a property ordered by sort_order."""
    return (
        db.query(PropertyVideo)
        .filter(PropertyVideo.property_id == property_id, PropertyVideo.is_deleted == False)
        .order_by(PropertyVideo.sort_order.asc(), PropertyVideo.id.asc())
        .all()
    )


@router.delete("/videos/{vid_id}", status_code=204)
def delete_property_video(
    vid_id: int,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Soft delete a property video."""
    vid = db.query(PropertyVideo).filter(PropertyVideo.id == vid_id).first()
    if not vid:
        raise HTTPException(status_code=404, detail="Video not found")
    vid.is_deleted = True
    # pyrefly: ignore [bad-assignment]
    vid.updated_by = str(current_user.id)
    db.commit()
    return None
