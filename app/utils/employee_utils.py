from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.employee import Employee

def generate_next_employee_id(db: Session) -> str:
    """
    Generate next employee_id in format EMP001, EMP002, etc.
    Based on the highest existing numeric suffix.
    """
    last_emp = db.query(Employee).order_by(Employee.employee_id.desc()).first()
    
    if not last_emp:
        return "EMP001"
    
    last_id = last_emp.employee_id
    try:
        # Extract numeric part (assuming prefix "EMP")
        if last_id.startswith("EMP"):
            suffix = last_id[3:]
            next_num = int(suffix) + 1
            return f"EMP{next_num:03d}"
    except (ValueError, IndexError):
        pass
        
    return f"EMP{db.query(func.count(Employee.id)).scalar() + 1:03d}"
