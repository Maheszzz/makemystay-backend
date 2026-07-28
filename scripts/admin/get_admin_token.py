from app.configs.db_config import SessionLocal
from app.models.user import User
from app.models.agent import Agent
from app.models.lead import Lead
from app.models.retell_call_test import RetellCallTest
from app.core import security

def main():
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.role == 'admin').first()
        if admin_user:
            token = security.create_access_token(data={"sub": admin_user.email, "role": admin_user.role})
            print(f"ADMIN_JWT={token}")
        else:
            print("No admin user found")
    finally:
        db.close()

if __name__ == "__main__":
    main()
