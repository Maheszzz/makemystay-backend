import mysql.connector
import os
import json
import argparse
import sys

# standalone locality mapping for the script
MAPPING = {
    "whitefield": "bangalore",
    "btm layout": "bangalore",
    "hsr layout": "bangalore",
    "marathahalli": "bangalore",
    "electronic city": "bangalore",
    "koramangala": "bangalore",
    "indiranagar": "bangalore",
    "jayanagar": "bangalore",
    "bellandur": "bangalore",
    "sarjapur road": "bangalore",
    "jp nagar": "bangalore",
    "hebbal": "bangalore",
    "banaswadi": "bangalore",
    "kammanahalli": "bangalore",
    "kalyan nagar": "bangalore",
    "brookefield": "bangalore",
    "kadugodi": "bangalore",
    "hoodi": "bangalore",
    "mahadevapura": "bangalore",
    "varthur": "bangalore",
    "gunjur": "bangalore",
    "panathur": "bangalore",
    "munnekolala": "bangalore",
    "kasavanahalli": "bangalore",
    "harlur": "bangalore",
    "kaikondrahalli": "bangalore",
    "doddanekundi": "bangalore",
    "kundalahalli": "bangalore",
    "vibhutipura": "bangalore",
    "basavanagara": "bangalore",
    "cv raman nagar": "bangalore",
    "kaggadasapura": "bangalore",
    "gm palya": "bangalore",
    "domlur": "bangalore",
    "murugeshpalya": "bangalore",
    "hal": "bangalore",
    "old airport road": "bangalore",
    "frazer town": "bangalore",
    "rt nagar": "bangalore",
    "sanjay nagar": "bangalore",
    "yeshwanthpur": "bangalore",
    "mathikere": "bangalore",
    "malleshwaram": "bangalore",
    "sadashiva nagar": "bangalore",
    "seshadripuram": "bangalore",
    "vasanth nagar": "bangalore",
    "shanti nagar": "bangalore",
    "wilson garden": "bangalore",
    "richmond town": "bangalore",
    "langford town": "bangalore",
    "cooke town": "bangalore",
    "richards town": "bangalore",
    "benson town": "bangalore",
    "cox town": "bangalore",
    "ulsoor": "bangalore",
    "banashankari": "bangalore",
    "padmanabhanagar": "bangalore",
    "kumaraswamy layout": "bangalore",
    "isro layout": "bangalore",
    "uttarahalli": "bangalore",
    "rajarajeshwari nagar": "bangalore",
    "kengeri": "bangalore",
    "vijayanagar": "bangalore",
    "basaveshwaranagar": "bangalore",
    "rajajinagar": "bangalore",
    "mahalakshmi layout": "bangalore",
    "nandini layout": "bangalore",
    "peenya": "bangalore",
    "dasarahalli": "bangalore",
    "t dasarahalli": "bangalore",
    "mallasandra": "bangalore",
    "bagalakunte": "bangalore",
    "chikkabanavara": "bangalore",
    "hesaraghatta road": "bangalore",
    "vidyaranyapura": "bangalore",
    "yelahanka": "bangalore",
    "sahakar nagar": "bangalore",
}

def find_city_for_location(location):
    if not location: return None
    loc_lower = location.lower()
    for locality, city in MAPPING.items():
        if locality in loc_lower:
            return city
    return None

def get_db_config():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.core.config import load_app_env

    load_app_env()

    return {
        "host": os.environ.get("DB_HOST", "127.0.0.1"),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "makemystay"),
        "port": int(os.environ.get("DB_PORT", "3306")),
    }

BACKUP_PATH = os.environ.get("BACKUP_PATH", "/tmp/city_backup.json")

def backup_data(cursor):
    print(f"📦 Creating backup at {BACKUP_PATH}...")
    cursor.execute("SELECT id, city, location FROM properties")
    rows = cursor.fetchall()
    backup = [dict(zip(['id', 'city', 'location'], row)) for row in rows]
    with open(BACKUP_PATH, 'w') as f:
        json.dump(backup, f, indent=2)
    print(f"✅ Backup complete. Total records: {len(backup)}")

def rollback_data(cursor):
    if not os.path.exists(BACKUP_PATH):
        print(f"❌ Error: Backup file {BACKUP_PATH} not found!")
        return
    
    print(f"🔄 Rolling back data from {BACKUP_PATH}...")
    with open(BACKUP_PATH, 'r') as f:
        backup = json.load(f)
        
    for item in backup:
        cursor.execute(
            "UPDATE properties SET city = %s WHERE id = %s",
            (item['city'], item['id'])
        )
    print(f"✅ Rollback complete. Restored {len(backup)} records.")

def fix_cities(cursor, dry_run=True):
    print(f"🔍 Checking for properties with missing city info... {'(DRY RUN)' if dry_run else ''}")
    cursor.execute("SELECT id, city, location FROM properties")
    rows = cursor.fetchall()
    
    updates = []
    for row in rows:
        row_id, city, location = row
        if not city:
            derived_city = find_city_for_location(location)
            if derived_city:
                updates.append((derived_city, row_id, location))
    
    if not updates:
        print("✨ No properties need fixing.")
        return

    print(f"📈 Found {len(updates)} properties to update.")
    for derived_city, row_id, location in updates:
        print(f"  - Property #{row_id}: {location} -> {derived_city}")
        if not dry_run:
            cursor.execute("UPDATE properties SET city = %s WHERE id = %s", (derived_city, row_id))
            
    if dry_run:
        print("\n⚠️ This was a DRY RUN. No changes were made.")
    else:
        print(f"\n✅ Successfully updated {len(updates)} properties.")

def main():
    parser = argparse.ArgumentParser(description="Fix property cities based on location.")
    parser.add_argument("--run", action="store_true", help="Perform the actual updates (not a dry run)")
    parser.add_argument("--rollback", action="store_true", help="Restore city data from backup")
    args = parser.parse_args()

    try:
        db_config = get_db_config()
        print(f"🔌 Connecting to {db_config['host']}:{db_config['port']} as {db_config['user']}...")
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        if args.rollback:
            rollback_data(cursor)
            conn.commit()
        else:
            if args.run:
                backup_data(cursor)
                fix_cities(cursor, dry_run=False)
                conn.commit()
            else:
                fix_cities(cursor, dry_run=True)
                
        cursor.close()
        conn.close()
    except mysql.connector.Error as err:
        print(f"❌ Database error: {err}")
    except Exception as e:
        print(f"❌ Error during operation: {e}")

if __name__ == "__main__":
    main()
