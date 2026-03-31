import os

import redis
from rq import Queue

# Initialize Redis connection
# In a real environment, you'd get the REDIS_URL from settings

ADMIN_CHANNEL = "admin_events"

# Redis lock key for Housing.com historical recovery (must match Celery task release).
HISTORICAL_HOUSING_SYNC_LOCK = "lock:historical_sync_housing"

try:
    redis_conn = redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        socket_timeout=2.0,
        socket_connect_timeout=2.0
    )
    # Verify connection on startup
    redis_conn.ping()
    
    # Main lead processing queue
    lead_queue = Queue("lead_sync", connection=redis_conn)
    # Background worker/sync queue
    sync_queue = Queue("worker_sync", connection=redis_conn)
except Exception as e:
    # Fallback to None if redis is not available (dev mode safety)
    redis_conn = None
    lead_queue = None
    sync_queue = None
    print(f"Warning: Redis not connected or failed ping: {e}")
