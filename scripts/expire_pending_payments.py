"""
Cleanup script to expire pending payments older than 24 hours.
Run this script daily via cron job or task scheduler.

Usage:
    python3 scripts/expire_pending_payments.py
"""
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.configs.db_config import get_db
from app.models.payment import Payment
from loguru import logger

def expire_old_pending_payments(hours=24):
    """
    Mark pending payments older than specified hours as expired.
    
    Args:
        hours (int): Number of hours after which a pending payment should be expired
    """
    db = next(get_db())
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        logger.info(f"Expiring pending payments created before {cutoff_time}")
        
        # Find all pending payments older than cutoff time
        old_pending = db.query(Payment).filter(
            Payment.status == 'pending',
            Payment.created_at < cutoff_time
        ).all()
        
        if not old_pending:
            logger.info("No pending payments to expire.")
            return 0
        
        # Update status to expired
        count = 0
        for payment in old_pending:
            payment.status = 'expired'
            count += 1
            logger.info(f"Expired payment #{payment.id} (order: {payment.order_id})")
        
        db.commit()
        logger.success(f"Successfully expired {count} pending payment(s).")
        return count
        
    except Exception as e:
        logger.error(f"Error expiring payments: {e}")
        db.rollback()
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    # Default: expire pending payments older than 24 hours
    expired_count = expire_old_pending_payments(hours=24)
    print(f"Expired {expired_count} payment(s).")
