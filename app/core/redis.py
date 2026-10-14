import os

import redis

ADMIN_CHANNEL = "admin_events"
HISTORICAL_HOUSING_SYNC_LOCK = "lock:historical_sync_housing"

try:
    from rq import Queue

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
