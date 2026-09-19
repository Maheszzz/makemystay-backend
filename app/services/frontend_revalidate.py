import httpx
from loguru import logger
import asyncio
from app.core.config import settings

async def _trigger_revalidate(tags: list[str]) -> None:
    if not settings.FRONTEND_REVALIDATE_URL:
        return
        
    url = settings.FRONTEND_REVALIDATE_URL
    secret = settings.FRONTEND_REVALIDATE_SECRET
    
    params = {}
    if secret:
        params["secret"] = secret
        
    try:
        async with httpx.AsyncClient() as client:
            # We assume Next.js app router revalidate API that supports either query tag or body tags
            # e.g., POST /api/revalidate
            # This is a common pattern for Next.js cache revalidation.
            payload = {"tags": tags}
            response = await client.post(url, params=params, json=payload, timeout=5.0)
            if response.status_code >= 400:
                logger.error(f"Frontend revalidation failed: {response.status_code} - {response.text}")
            else:
                logger.info(f"Frontend revalidation successful for tags: {tags}")
    except Exception as e:
        logger.error(f"Failed to call frontend revalidation webhook: {e}")

def revalidate_frontend_cache_sync(tags: list[str]) -> None:
    """
    Fire-and-forget sync wrapper for frontend revalidation.
    Suitable for calling from synchronous FastAPI endpoints or SQLAlchemy event listeners.
    """
    if not settings.FRONTEND_REVALIDATE_URL:
        return
        
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_trigger_revalidate(tags))
    except RuntimeError:
        # No running event loop, create one to run the async task
        asyncio.run(_trigger_revalidate(tags))
