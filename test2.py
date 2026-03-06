import sys
from app.schemas.realty import ContactCreate
from app.models.realty import Contact

try:
    data = {"name":"test name","phone":"1234567890","email":"test@example.com","location":"BTM","property_type":"PG","units":"","current_occupancy":"","monthly_revenue":"","uses_brokers":"","message":"hello"}
    c = ContactCreate(**data)
    d = c.model_dump(by_alias=False)
    print("Dump:", d)
    db_contact = Contact(**d)
    print(db_contact.name_)
except Exception as e:
    import traceback
    traceback.print_exc()
