from app.configs.db_config import MySQLSessionLocal
from app.repo.user import create_user, get_user_by_email
from app.core.security import get_password_hash
import sys

def seed_admin():
    db = MySQLSessionLocal()
    try:
        admin_email = "admin@makemystay.ai"
        admin_password = "AdminChangeMe123!" # Default password
        
        existing_user = get_user_by_email(db, admin_email)
        if existing_user:
            print(f"User {admin_email} already exists.")
            return

        user_data = {
            "email": admin_email,
            "password_hash": get_password_hash(admin_password),
            "role": "admin",
            "full_name": "System Admin"
        }
        
        create_user(db, user_data)
        print(f"Admin user created: {admin_email}")
        print(f"Default Password: {admin_password}")

    except Exception as e:
        print(f"Error seeding admin: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_admin()
