from loguru import logger
import httpx
from app.core.config import settings

class AlertService:
    """Service to send real-time business alerts (Hot Leads, Deals) via WhatsApp."""

    async def _send_whatsapp(self, message: str):
        """Internal helper to send a Meta WhatsApp message to the sales team."""
        if not settings.WHATSAPP_TOKEN or not settings.PHONE_NUMBER_ID or not settings.SALES_TEAM_PHONE:
            logger.warning("WhatsApp Alert skipped: Meta API or SALES_TEAM_PHONE not configured.")
            return

        url = (
            f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/"
            f"{settings.PHONE_NUMBER_ID}/messages"
        )
        headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
        
        payload = {
            "messaging_product": "whatsapp",
            "to": settings.SALES_TEAM_PHONE,
            "type": "text",
            "text": {"body": message},
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code >= 400:
                    logger.error(f"WhatsApp Alert failed: {resp.status_code} {resp.text}")
                else:
                    logger.info(f"WhatsApp Alert sent to {settings.SALES_TEAM_PHONE}")
        except Exception as e:
            logger.error(f"WhatsApp Alert exception: {str(e)}")

    def send_deal_created_alert(self, name: str, phone: str, project: str):
        """Sends an instant alert when a new Deal is created in the pipeline."""
        message = (
            "💰 NEW DEAL CREATED 💰\n\n"
            f"👤 Lead: {name}\n"
            f"📞 Phone: {phone}\n"
            f"🏢 Project: {project if project else 'N/A'}\n"
            "📅 Stage: Qualification\n\n"
            "Respond now for maximum conversion! 🚀"
        )
        # We wrap the async call in a task or run_until_complete if called from sync
        import asyncio
        import threading
        
        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._send_whatsapp(message))
            loop.close()

        threading.Thread(target=run_async).start()

    def send_hot_lead_alert(self, name: str, phone: str, source: str):
        """Sends an instant alert for a high-priority 'Hot Lead' arrival."""
        message = (
            "🔥 CORE ALERT: HOT LEAD 🔥\n\n"
            f"👤 Name: {name}\n"
            f"📞 Phone: {phone}\n"
            f"📍 Source: {source}\n\n"
            "Immediate touch requested! ⚡"
        )
        import asyncio
        import threading

        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._send_whatsapp(message))
            loop.close()

        threading.Thread(target=run_async).start()

alert_service = AlertService()
