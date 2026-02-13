import requests
import boto3
import os
import mimetypes
from dotenv import load_dotenv

# Load env vars
load_dotenv()

API_BASE = "http://localhost:8000/api/v1/realty"
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

# Initialize S3
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=AWS_REGION
)

def upload_image_to_s3(filepath):
    """Uploads file to S3 and returns the Key"""
    filename = os.path.basename(filepath)
    content_type, _ = mimetypes.guess_type(filepath)
    if not content_type:
        content_type = "application/octet-stream"
        
    s3_key = f"properties/seed/{filename}"
    
    print(f"  ☁️ Uploading {filename} to S3...")
    s3.upload_file(
        filepath, 
        BUCKET_NAME, 
        s3_key, 
        ExtraArgs={"ContentType": content_type}
    )
    return s3_key

def create_property(data):
    """Creates property via API"""
    print(f"  🏠 Creating property: {data['property_name']}...")
    resp = requests.post(f"{API_BASE}/properties", json=data)
    if resp.status_code != 201:
        print(f"  ❌ Failed to create property: {resp.text}")
        return None
    return resp.json()

def add_image_to_property(property_id, s3_key, is_primary=False):
    """Links image to property via API"""
    payload = {
        "image_url": s3_key,
        "is_primary": is_primary,
        "sort_order": 0
    }
    resp = requests.post(f"{API_BASE}/properties/{property_id}/images", json=payload)
    if resp.status_code != 201:
        print(f"  ❌ Failed to link image: {resp.text}")

def seed():
    # Example Data
    # You can change this or loop through a folder
    
    # 1. Define Property
    prop_data = {
        "property_name": "Luxury Villa with Pool",
        "location": "Whitefield, Bangalore",
        "property_type": "Villa",
        "listing_type": "rent",
        "private_price": 45000,
        "phone": "9876543210",
        "description": "Amazing villa using Secure S3 Uploads and CloudFront!",
        "is_available": True
    }

    # 2. Define Images (Local Paths)
    # Based on your screenshot, I've added these paths.
    # Please verify if they are correct on your machine!
    images = [
        "/Users/maheswaranm/Downloads/Arcade Inn Coliving.jpg",
        "/Users/maheswaranm/Downloads/Avinya co live.jpg",
        "/Users/maheswaranm/Downloads/Co living Hub 0.2.jpg",
        "/Users/maheswaranm/Downloads/Connect coliving 2.jpg",
        '/Users/maheswaranm/Downloads/Pro colive (new).jpg'
        '/Users/maheswaranm/Downloads/DVR coliving.jpg'
        '/Users/maheswaranm/Downloads/Connect coliving.jpeg'
        '/Users/maheswaranm/Downloads/Shine premium colive.jpg'
        '/Users/maheswaranm/Downloads/Varadhi premium co living pg.jpg'
        '/Users/maheswaranm/Downloads/Urban living.jpg'
        '/Users/maheswaranm/Downloads/SGR enclave coliving.jpg'
        '/Users/maheswaranm/Downloads/Premium Urban Coliving.jpg'
        '/Users/maheswaranm/Downloads/kings & Queens Coliving.jpg'
        '/Users/maheswaranm/Downloads/Haveli Coliving.jpg'
        '/Users/maheswaranm/Downloads/Flock 9 Coliving.jpg'
        '/Users/maheswaranm/Downloads/Aveniya.jpeg'
        '/Users/maheswaranm/Downloads/dvr.jpeg'
        '/Users/maheswaranm/Downloads/Connect Coliving 2,.jpeg'
        '/Users/maheswaranm/Downloads/shine premium colive.jpeg'
        '/Users/maheswaranm/Downloads/hevenhome.jpeg'


    ]
    
    if not BUCKET_NAME:
        print("❌ Error: S3_BUCKET_NAME not found in .env")
        return

    # --- Execution ---
    print("🚀 Starting Seed...")
    
    # Create Property
    prop = create_property(prop_data)
    if not prop: return
    
    prop_id = prop['id']
    print(f"  ✅ Property Created (ID: {prop_id})")
    
    # Upload & Link Images
    if not images:
        print("  ⚠️ No images defined in script. Skipping uploads.")
        
    for idx, img_path in enumerate(images):
        if not os.path.exists(img_path):
            print(f"  ⚠️ File not found: {img_path}")
            continue
            
        try:
            # Upload to S3
            key = upload_image_to_s3(img_path)
            
            # Link to DB
            add_image_to_property(prop_id, key, is_primary=(idx==0))
            print(f"  ✅ Linked image: {key}")
            
        except Exception as e:
            print(f"  ❌ Error uploading {img_path}: {e}")

    print("\n✨ Seed Complete!")

if __name__ == "__main__":
    seed()
