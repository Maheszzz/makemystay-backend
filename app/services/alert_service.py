import httpx
from loguru import logger
from app.core.config import settings

class AlertService:
    """Singleton service for sending proactive system alerts to Slack/Discord webhooks.
    Used for monitoring sync failures, lead ingestion gaps, and other critical events.
    """
    
    def __init__(self):
        self.webhook_url = settings.ALERT_WEBHOOK_URL
        self.is_enabled = bool(self.webhook_url)

    async def send_alert(self, message: str, level: str = "info"):
        """Sends a notification to the configured webhook URL.
        Level can be: info, warning, error, critical
        """
        if not self.is_enabled:
            logger.info(f"System Alert (local only): [{level.upper()}] {message}")
            return

        # Slack/Discord compatible payload
        emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "🚨",
            "critical": "🔥"
        }.get(level.lower(), "📢")

        payload = {
            "text": f"{emoji} *SYSTEM ALERT ({level.upper()})*\n\n{message}",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                if response.status_code >= 400:
                    logger.error(f"Webhook error ({response.status_code}): {response.text}")
                else:
                    logger.success(f"Alert sent successfully: {message[:50]}...")
        except Exception as e:
            logger.error(f"Failed to post system alert: {e}")

# Singleton instance
alert_service = AlertService()
