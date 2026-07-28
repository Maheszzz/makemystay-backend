import mimetypes
import os

import boto3
import pymysql
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_BASE = "http://localhost:8000/api/v1/realty"
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

# Database Config
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Definitive Image List (UPDATED)
IMAGES = [
    "/Users/maheswaranm/Downloads/Arcade Inn Coliving.jpg",
    "/Users/maheswaranm/Downloads/Co living Hub 0.2.jpg",
    "/Users/maheswaranm/Downloads/Connect coliving 2.jpg",  # Keep older one? No, user provided new. Wait, user provided "Connect Coliving 2,.jpeg"
    "/Users/maheswaranm/Downloads/Connect Coliving 2,.jpeg",  # NEW
    "/Users/maheswaranm/Downloads/Connect coliving.jpeg",  # NEW
    "/Users/maheswaranm/Downloads/dvr.jpeg",  # NEW
    "/Users/maheswaranm/Downloads/shine premium colive.jpeg",  # NEW
    "/Users/maheswaranm/Downloads/Aveniya.jpeg",  # NEW
    # Keeping old ones that might not have changed or user didn't mention updating
    "/Users/maheswaranm/Downloads/Varadhi premium co living pg.jpg",
    "/Users/maheswaranm/Downloads/Urban living.jpg",
    "/Users/maheswaranm/Downloads/SGR enclave coliving.jpg",
    "/Users/maheswaranm/Downloads/Premium Urban Coliving.jpg",
    "/Users/maheswaranm/Downloads/kings & Queens Coliving.jpg",
    "/Users/maheswaranm/Downloads/Haveli Coliving.jpg",
    "/Users/maheswaranm/Downloads/Flock 9 Coliving.jpg",
]


def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_property_map():
    """Returns a dict matching {property_name_lower: property_id}"""
    print("🔍 Fetching properties from database...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, property_name FROM properties")
            results = cursor.fetchall()
            prop_map = {
                row["property_name"].strip().lower(): row["id"] for row in results
            }
            print(f"   Found {len(prop_map)} properties in DB.")
            return prop_map
    finally:
        conn.close()


# Manual Mappings
MANUAL_MAP = {
    "pro coliving": "pro colive pg",
    "sgr enclave coliving": "sgr enclave",
    "connect coliving 2": "connect coliving",  # Wait, no! "Connect Coliving 2" IS a property now.
    # remove "connect coliving 2" -> "connect coliving" mapping if they are distinct.
    "connect coliving": "connect coliving",
    "connect coliving 2,": "connect coliving 2",  # Handle typo in filename
    "aveniya": "avinya co live",
    "dvr": "dvr coliving",
    "shine premium colive": "shine premium colive",
}


def create_property_api(name):
    """Creates a basic property so we can link the image"""
    print(f"   🏗️ Creating new property: '{name}'...")
    payload = {
        "property_name": name,
        "location": "Bangalore (Auto-Created)",
        "property_type": "PG",
        "listing_type": "rent",
        "is_available": True,
        "phone": "9999999999",
        "description": "Auto-created from image upload.",
    }
    resp = requests.post(f"{API_BASE}/properties", json=payload)
    if resp.status_code == 201:
        new_id = resp.json()["id"]
        print(f"   ✅ Created Property ID: {new_id}")
        return new_id
    else:
        print(f"   ❌ Failed to create property: {resp.text}")
        return None


def upload_to_s3(filepath, property_id):
    """Uploads file to properties/{id}/{filename}"""
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

    key = f"properties/{property_id}/{filename}"

    print(f"   ☁️ Uploading to S3: {key}")
    s3.upload_file(filepath, BUCKET_NAME, key, ExtraArgs={"ContentType": content_type})
    return key


def cleanup_old_images(property_id):
    """Deletes existing images for a property from DB"""
    print(f"   🧹 Cleaning up old images for Property ID {property_id}...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM property_images WHERE property_id = %s", (property_id,)
            )
        conn.commit()
    except Exception as e:
        print(f"      ❌ Failed to cleanup DB: {e}")
    finally:
        conn.close()


def link_image_api(property_id, s3_key):
    """Calls API to link image to property"""
    payload = {"image_url": s3_key, "is_primary": True, "sort_order": 0}
    resp = requests.post(f"{API_BASE}/properties/{property_id}/images", json=payload)
    if resp.status_code == 201:
        print(f"   ✅ Linked successfully! (ID: {resp.json().get('id')})")
    else:
        print(f"   ❌ API Error: {resp.status_code} - {resp.text}")


def main():
    print("🚀 Starting Image Update Script (Cleanup & Re-Upload)...\n")

    prop_map = get_property_map()

    # Track which properties we've already cleaned to avoid double deletion
    cleaned_properties = set()

    print("\nProcessing Images:")
    for img_path in IMAGES:
        if not os.path.exists(img_path):
            print(f"\n⚠️  File not found: {img_path}")
            continue

        filename = os.path.basename(img_path)
        name_part = os.path.splitext(filename)[0]
        lookup_name = name_part.strip().lower()

        print(f"\n📄 Processing: {filename}")

        # Check explicit manual map first
        prop_id = None
        if lookup_name in MANUAL_MAP:
            mapped_name = MANUAL_MAP[lookup_name]
            print(f"   Using manual map: '{lookup_name}' -> '{mapped_name}'")
            prop_id = prop_map.get(mapped_name)

        if not prop_id:
            prop_id = prop_map.get(lookup_name)

        if not prop_id:
            # AUTO-CREATE Logic
            print(f"   ❌ No matching property found for '{name_part}' - Creating...")
            # Use original casing, or mapped name if available?
            create_name = MANUAL_MAP.get(lookup_name, name_part)
            prop_id = create_property_api(create_name)
            if not prop_id:
                continue
            prop_map[lookup_name] = prop_id  # Update local map

        print(f"   Target Property ID: {prop_id}")

        try:
            # CLEANUP: Only once per property
            if prop_id not in cleaned_properties:
                cleanup_old_images(prop_id)
                cleaned_properties.add(prop_id)

            # 1. Upload
            s3_key = upload_to_s3(img_path, prop_id)

            # 2. Link
            link_image_api(prop_id, s3_key)

        except Exception as e:
            print(f"   ❌ Error: {e}")

    print("\n✨ Done!")


if __name__ == "__main__":
    main()
