"""
Lead Capture Service (Sprint 9).
Automatically generates a CRM Lead when a user downloads premium documents
(Brochure, Pricing, WAP) or books a visit. Assigns the lead to an active employee (RM).
"""

from typing import Optional
from sqlalchemy.orm import Session
from loguru import logger

from app.models.lead import Lead
from app.models.employee import Employee
from app.models.realty_enterprise import PropertyLead, PropertyDownload


def capture_document_download_lead(
    db: Session,
    property_id: int,
    document_type: str,
    user_name: str,
    user_phone: str,
    user_email: str,
    user_company: Optional[str] = None,
    purpose: Optional[str] = None,
) -> PropertyLead:
    """
    1. Log the download in PropertyDownload table (Sprint 8).
    2. Create or link a CRM Lead in Lead table (Sprint 9).
    3. Assign to an active RM employee.
    4. Link in PropertyLead table.
    """
    # 1. Log Download
    download_entry = PropertyDownload(
        property_id=property_id,
        document_type=document_type,
        user_name=user_name,
        user_phone=user_phone,
        user_email=user_email,
        user_company=user_company,
        purpose=purpose,
    )
    db.add(download_entry)

    # 2. Find an active RM Employee for assignment
    active_rm = (
        db.query(Employee)
        .filter(Employee.status == "active", Employee.role == "RM")
        .first()
    )
    assigned_id = active_rm.id if active_rm else None

    # 3. Check if Lead already exists by phone/email
    existing_lead = (
        db.query(Lead)
        .filter((Lead.phone == user_phone) | (Lead.email == user_email))
        .first()
    )

    if not existing_lead:
        new_lead = Lead(
            name=user_name,
            phone=user_phone,
            email=user_email,
            source=f"property_{document_type}_download",
            assigned_employee_id=assigned_id,
            status="new",
            message=f"Downloaded {document_type} for property {property_id} ({purpose or 'General interest'})",
        )
        db.add(new_lead)
        db.flush()
        lead_id = new_lead.id
    else:
        lead_id = existing_lead.id

    # 4. Create PropertyLead bridge
    prop_lead = PropertyLead(
        property_id=property_id,
        lead_id=lead_id,
        source=f"{document_type}_download",
        assigned_employee_id=assigned_id,
        status="New",
    )
    db.add(prop_lead)
    db.commit()
    db.refresh(prop_lead)

    logger.info(
        f"LEAD CAPTURED | prop_id={property_id} type={document_type} "
        f"phone={user_phone} lead_id={lead_id} assigned_rm={assigned_id}"
    )
    return prop_lead
