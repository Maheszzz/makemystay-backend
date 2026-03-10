from app.schemas.realty import ContactCreate
contact = ContactCreate(name="test", phone="1234567890", email="a@b.com", message="test")
print(contact.name_)
try:
    print(contact.name)
except AttributeError as e:
    print("AttributeError:", e)
