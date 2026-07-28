import re
import pymysql

# Connect to DB
conn = pymysql.connect(
    host='127.0.0.1',
    port=3310,
    user='appuser',
    password='StrongPassword@123',
    database='makemystay'
)
cur = conn.cursor()

def process_row(table, values):
    if not values: return
    try:
        if table == 'properties':
            p_id = values.get('1', 'NULL')
            name = values.get('2', 'NULL').strip("'")
            location = values.get('3', 'NULL').strip("'")
            phone = values.get('5', '00000').strip("'")
            cur.execute(
                "INSERT IGNORE INTO properties (id, property_name, location, phone, property_type, listing_type) VALUES (%s, %s, %s, %s, 'PG', 'rent')",
                (p_id, name, location, phone)
            )
        elif table == 'property_images':
            i_id = values.get('1', 'NULL')
            prop_id = values.get('2', 'NULL')
            url = values.get('3', 'NULL').strip("'")
            is_pri = values.get('4', '0')
            sort = values.get('5', '0')
            
            # Check if property_id exists before inserting!
            cur.execute("SELECT id FROM properties WHERE id=%s", (prop_id,))
            if cur.fetchone():
                cur.execute(
                    "INSERT IGNORE INTO property_images (id, property_id, image_url, is_primary, sort_order) VALUES (%s, %s, %s, %s, %s)",
                    (i_id, prop_id, url, is_pri, sort)
                )
        elif table == 'contacts':
            c_id = values.get('1', 'NULL')
            name = values.get('2', 'Unknown').strip("'")
            phone = values.get('3', 'Unknown').strip("'")
            email = values.get('4', 'Unknown').strip("'")
            cur.execute(
                "INSERT IGNORE INTO contacts (id, name_, phone, email, message, status) VALUES (%s, %s, %s, %s, '', 'new')",
                (c_id, name, phone, email)
            )
    except Exception as e:
        print(f"Error inserting into {table}: {e}")

current_table = None
current_values = {}

with open('decoded_binlogs.txt', 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        line = line.strip()
        if line.startswith('### INSERT INTO `makemystay`.'):
            process_row(current_table, current_values)
            
            table_match = re.search(r'### INSERT INTO `makemystay`\.`(\w+)`', line)
            current_table = table_match.group(1) if table_match else None
            current_values = {}
        
        elif line.startswith('###   @'):
            if current_table:
                parts = line.split('=', 1)
                if len(parts) == 2:
                    idx = parts[0].replace('###   @', '').strip()
                    val = parts[1].split(' /*')[0].strip()
                    current_values[idx] = val

# Process the final row
process_row(current_table, current_values)

conn.commit()
cur.close()
conn.close()
print("Salvage complete.")
