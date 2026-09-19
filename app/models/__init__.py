# Registry of all models for Alembic to detect and generate schemas from
from app.models.booking import Booking
from app.models.demo import DemoBooking
from app.models.failed_job import FailedJob
from app.models.ledger import LedgerEntry
from app.models.payment import Payment
from app.models.payment_webhook_event import PaymentWebhookEvent
from app.models.realty import Property, PropertyImage, Review, Contact
from app.models.realty_enterprise import (
    PropertyPricing,
    PropertyDocument,
    PropertyVideo,
    AmenityMaster,
    PropertyAmenity,
    PropertyNearbyPlace,
    PropertySEO,
    PropertyShare,
    PropertyAuditLog,
    PropertyUnit,
    PropertyTag,
    PropertyView,
    PropertyDownload,
)
from app.models.reconciliation import ReconciliationIssue
from app.models.retell_call import RetellCall
from app.models.sync_job import SyncJob
from app.models.user import User
