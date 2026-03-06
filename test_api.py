import sys
import traceback
from app.configs.db_config import get_mysql_db
from app.schemas.realty import ContactCreate
from app.api.realty import create_contact

try:
    data = {"name": "test name", "phone": "1234567890", "email": "test@example.com", "location": "BTM", "property_type": "PG", "units": "", "current_occupancy": "", "monthly_revenue": "", "uses_brokers": "", "message": "hello"}
    c = ContactCreate(**data)
    
    class MockBT:
        def add_task(self, func, *args, **kwargs):
            print(f"Added task {func.__name__} with {kwargs}")

    # Not using FastAPI depends directly, doing it manually:
    db_gen = get_mysql_db()
    db = next(db_gen)
    res = create_contact(contact=c, background_tasks=MockBT(), db=db)
    print("Success:", res)
except Exception as e:
    traceback.print_exc()
