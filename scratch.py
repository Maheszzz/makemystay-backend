import pymysql

conn = pymysql.connect(
    host='127.0.0.1',
    port=3336,
    user='appuser',
    password='StrongPassword@123',
    database='makemystay'
)
with conn.cursor() as cur:
    try:
        cur.execute('ALTER TABLE retell_calls DROP FOREIGN KEY retell_calls_ibfk_1')
    except Exception as e:
        print(e)
    try:
        cur.execute('ALTER TABLE retell_calls DROP COLUMN lead_id')
    except Exception as e:
        print(e)
conn.commit()
print("Done")
