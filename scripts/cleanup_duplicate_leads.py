from app.configs.db_config import SessionLocal, mysql_engine
from sqlalchemy import text, inspect
import sys

def sql_based_cleanup():
    db = SessionLocal()
    try:
        inspector = inspect(mysql_engine)
        tables_to_update = [t for t in inspector.get_table_names() if 'lead_id' in [c['name'] for c in inspector.get_columns(t)]]
        
        print(f"Tables to update: {tables_to_update}")

        # 1. Reassign related records from older leads to the NEWEST lead for that phone
        # We join leads (older) with leads (newer) on phone and l1.id < l2.id
        # Then update the dependent table.
        # We do this for all dependent tables.
        
        # We use a temporary table or subquery to determine the FINAL survivor for each phone
        # to avoid multiple updates.
        
        print("Finding survivor mappings...")
        db.execute(text("CREATE TEMPORARY TABLE IF NOT EXISTS survivor_mapping (phone VARCHAR(20) PRIMARY KEY, survivor_id INT)"))
        db.execute(text("DELETE FROM survivor_mapping"))
        db.execute(text("INSERT INTO survivor_mapping SELECT phone, MAX(id) FROM leads GROUP BY phone HAVING COUNT(id) > 1"))
        
        mapping_count = db.execute(text("SELECT COUNT(*) FROM survivor_mapping")).scalar()
        print(f"Mapped {mapping_count} phones for re-assignment.")
        
        if mapping_count > 0:
            for table in tables_to_update:
                update_sql = text(f"""
                    UPDATE {table} t
                    INNER JOIN leads l ON t.lead_id = l.id
                    INNER JOIN survivor_mapping sm ON l.phone = sm.phone
                    SET t.lead_id = sm.survivor_id
                    WHERE t.lead_id != sm.survivor_id
                """)
                res = db.execute(update_sql)
                print(f"Updated {res.rowcount} records in {table}.")

            # 2. Delete the duplicates
            delete_sql = text("""
                DELETE l FROM leads l
                INNER JOIN survivor_mapping sm ON l.phone = sm.phone
                WHERE l.id != sm.survivor_id
            """)
            res = db.execute(delete_sql)
            print(f"Deleted {res.rowcount} duplicate leads.")
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    sql_based_cleanup()
