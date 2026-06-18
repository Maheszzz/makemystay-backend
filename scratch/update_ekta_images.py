import os
import glob
import mimetypes
import boto3
import pymysql
from datetime import datetime
from dotenv import load_dotenv

# Load env variables
load_dotenv()

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
CLOUDFRONT_DOMAIN = os.getenv("CLOUDFRONT_DOMAIN", "d1yfdszs9lcm9e.cloudfront.net")

# Database Config
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3336))
DB_USER = os.getenv("DB_USER", "appuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "StrongPassword@123")
DB_NAME = os.getenv("DB_NAME", "makemystay")

PROPERTY_ID = 298

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
    )

def cleanup_old_images():
    print(f"🧹 Deleting old images for property {PROPERTY_ID} in database...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM property_images WHERE property_id = %s", (PROPERTY_ID,)
            )
        conn.commit()
        print("✅ Old images deleted successfully.")
    except Exception as e:
        print(f"❌ Failed to cleanup: {e}")
    finally:
        conn.close()

def upload_to_s3(filepath):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=AWS_REGION,
    )

    filename = os.path.basename(filepath)
    content_type, _ = mimetypes.guess_type(filepath)
    if not content_type:
        content_type = "application/octet-stream"

    s3_key = f"properties/{PROPERTY_ID}/{filename}"
    print(f"☁️ Uploading {filename} to S3 bucket {BUCKET_NAME} as {s3_key}...")
    s3.upload_file(filepath, BUCKET_NAME, s3_key, ExtraArgs={"ContentType": content_type})
    return s3_key

def link_image_db(s3_key, filepath, is_primary, sort_order):
    image_url = f"https://{CLOUDFRONT_DOMAIN}/{s3_key}"
    file_size = os.path.getsize(filepath)
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO property_images 
            (property_id, image_url, is_primary, sort_order, is_deleted, content_type, mime_validated, file_size, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                PROPERTY_ID,
                image_url,
                1 if is_primary else 0,
                sort_order,
                0,
                "image/jpeg",
                1,
                file_size,
                datetime.now()
            ))
        conn.commit()
        print(f"✅ Linked successfully in DB! (Primary: {is_primary}, Sort Order: {sort_order}, URL: {image_url})")
    except Exception as e:
        print(f"❌ Failed to link image in DB: {e}")
    finally:
        conn.close()

def main():
    print("🚀 Starting image update for Ekta Homes (Property 298)...")
    
    # 1. Find the local files
    download_dir = "/Users/maheswaranm/Downloads"
    search_pattern = os.path.join(download_dir, "WhatsApp Image 2026-06-13 at 15.57*.jpeg")
    local_images = glob.glob(search_pattern)
    local_images = sorted(list(set(local_images)))
    
    if not local_images:
        print("❌ No images found matching 'WhatsApp Image 2026-06-13 at 15.57*.jpeg' in Downloads.")
        return
        
    print(f"Found {len(local_images)} images to upload.")

    # 2. Delete old images
    cleanup_old_images()

    # 3. Upload & link in DB
    for idx, filepath in enumerate(local_images):
        is_primary = (idx == 0) # set the first one as primary
        try:
            s3_key = upload_to_s3(filepath)
            link_image_db(s3_key, filepath, is_primary, idx)
        except Exception as e:
            print(f"❌ Error processing {filepath}: {e}")

    print("✨ Finished image update!")

if __name__ == "__main__":
    main()
