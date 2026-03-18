from loguru import logger
from app.utils.zoho_crm_service import zoho_crm_service
from app.repo import lead as lead_repo
from app.configs.db_config import MySQLSessionLocal
from app.schemas.lead import LeadCreate

from app.utils.zoho_crm_service import zoho_crm_service, _CRMLeadAdapter

def sync_lead_to_zoho_task(lead_id: int):
    """RQ Task: Sync a stored lead to Zoho CRM using only its ID."""
    logger.info(f"RQ Task: Syncing Lead #{lead_id} to Zoho CRM...")
    
    with MySQLSessionLocal() as session:
        lead_obj = lead_repo.get_lead_by_id(session, lead_id)
        if not lead_obj:
            logger.error(f"Lead #{lead_id} not found in database. Sync aborted.")
            return

        try:
            # Use the lead object directly with the adapter
            # Injecting lead_id as external_id for Zoho idempotency
            adapter = _CRMLeadAdapter(lead_obj, lead_obj.source)
            if hasattr(adapter, 'raw_data'):
                if isinstance(adapter.raw_data, dict):
                    adapter.raw_data["external_id"] = lead_id
                else:
                    setattr(adapter.raw_data, "external_id", str(lead_id))

            import asyncio
            # Enforce 5s timeout for CRM sync
            zoho_lead_id = asyncio.run(asyncio.wait_for(
                zoho_crm_service.create_or_update_lead(adapter),
                timeout=5.0
            ))
            
            if zoho_lead_id:
                logger.info(f"Lead #{lead_id} successfully synced to Zoho CRM: {zoho_lead_id}")
                lead_repo.update_lead(
                    session, lead_obj, {
                        "zoho_lead_id": zoho_lead_id,
                        "zoho_synced": True,
                        "crm_status": "success"
                    }
                )
                session.commit()
            else:
                logger.error(f"Failed to sync Lead #{lead_id} to Zoho CRM (No ID returned)")
                lead_repo.update_lead(session, lead_obj, {"crm_status": "failed"})
                session.commit()
                
        except Exception as e:
            logger.error(f"RQ Task Error [sync_lead_to_zoho_task] for Lead #{lead_id}: {e}")
            lead_repo.update_lead(session, lead_obj, {"crm_status": "failed"})
            session.commit()
            raise

def process_contact_notifications_task(contact_data_dict: dict, contact_id: int):
    """RQ Task: Handle all post-creation notifications for a website contact."""
    logger.info(f"RQ Task: Processing notifications for Contact #{contact_id}...")
    
    from app.utils.email_utils import email_service
    from app.api.retell import trigger_outbound_call
    from app.repo import realty as realty_repo
    
    # Simple object to mimic Pydantic for the adapter
    class SimpleObj:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)
    
    contact_obj = SimpleObj(contact_data_dict)
    
    import asyncio
    
    async def _run_async_tasks():
        tasks = [
            email_service.send_contact_notification(contact_obj),
            zoho_crm_service.create_or_update_lead(_CRMLeadAdapter(contact_obj, "website"))
        ]
        
        # AI Call logic
        if not getattr(contact_obj, "is_ai_called", False):
            tasks.append(trigger_outbound_call(
                name=getattr(contact_obj, "name_", "User"),
                phone=getattr(contact_obj, "phone", ""),
                location=getattr(contact_obj, "location", ""),
                property_type=getattr(contact_obj, "property_type", ""),
                message=getattr(contact_obj, "message", "")
            ))
            tasks.append(zoho_crm_service.log_call(contact_obj))
            
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Update DB state
        with MySQLSessionLocal() as session:
            db_contact = realty_repo.get_contact_by_id(session, contact_id)
            if db_contact:
                realty_repo.update_contact(session, db_contact, {"is_ai_called": True})

    try:
        asyncio.run(_run_async_tasks())
        logger.info(f"RQ Task: Notifications complete for Contact #{contact_id}")
    except Exception as e:
        logger.error(f"RQ Task Error [process_contact_notifications_task]: {e}")
        raise
