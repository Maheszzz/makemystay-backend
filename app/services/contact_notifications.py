import asyncio
from loguru import logger
from app.utils.email_utils import email_service
from app.utils.zoho_crm_service import zoho_crm_service
from app.utils.zoho_adapter import CRMLeadAdapter
from app.api.retell import trigger_outbound_call
from app.configs.db_config import MySQLSessionLocal
from app.repo import realty as realty_repo

class SimpleObj:
    def __init__(self, d: dict):
        for k, v in d.items():
            setattr(self, k, v)

async def async_process_contact_notifications(contact_data_dict: dict, contact_id: int):
    logger.info(f"BackgroundTasks: Processing notifications for Contact #{contact_id}...")
    contact_obj = SimpleObj(contact_data_dict)

    tasks = [
        email_service.send_contact_notification(contact_obj),
        zoho_crm_service.create_or_update_lead(
            CRMLeadAdapter(contact_obj, getattr(contact_obj, "source", "website"))
        ),
    ]

    if not getattr(contact_obj, "is_ai_called", False):
        tasks.append(
            trigger_outbound_call(
                name=getattr(contact_obj, "name_", "User"),
                phone=getattr(contact_obj, "phone", ""),
                location=getattr(contact_obj, "location", ""),
                property_type=getattr(contact_obj, "property_type", ""),
                message=getattr(contact_obj, "message", ""),
            )
        )
        tasks.append(zoho_crm_service.log_call(contact_obj))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            task_name = "Unknown"
            if i == 0: task_name = "Email Notification"
            elif i == 1: task_name = "Zoho CRM Sync"
            elif i == 2: task_name = "Retell AI Call Trigger"
            elif i == 3: task_name = "Zoho Call Logging"
            logger.error(f"Post-creation task '{task_name}' failed for Contact #{contact_id}: {res}")

    # Update DB state
    try:
        with MySQLSessionLocal() as session:
            db_contact = realty_repo.get_contact_by_id(session, contact_id)
            if db_contact:
                realty_repo.update_contact(
                    session, db_contact, {"is_ai_called": True}
                )
    except Exception as e:
        logger.error(f"Failed to update contact #{contact_id} AI state: {e}")

def run_contact_notifications(contact_data_dict: dict, contact_id: int):
    """Synchronous wrapper for BackgroundTasks."""
    asyncio.run(async_process_contact_notifications(contact_data_dict, contact_id))
