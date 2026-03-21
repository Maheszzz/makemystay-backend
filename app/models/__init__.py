# Registry of all models for Alembic to detect and generate schemas from
from app.models.agent import Agent
from app.models.booking import Booking
from app.models.demo import DemoBooking
from app.models.failed_job import FailedJob
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.models.ledger import LedgerEntry
from app.models.payment import Payment
from app.models.payment_webhook_event import PaymentWebhookEvent
from app.models.realty import Property, PropertyImage
from app.models.reconciliation import ReconciliationIssue
from app.models.retell_call import RetellCall
from app.models.sync_job import SyncJob
from app.models.sync_metadata import SyncMetadata
from app.models.user import User
