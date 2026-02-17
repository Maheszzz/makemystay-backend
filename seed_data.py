import requests
import boto3
import os
import mimetypes
from dotenv import load_dotenv
from difflib import SequenceMatcher

# Load env vars
load_dotenv()

API_BASE = "http://127.0.0.1:8000/api/v1/realty"
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
    
    # print(f"  ☁️ Uploading {filename}...")
    s3.upload_file(
        filepath, 
        BUCKET_NAME, 
        s3_key, 
        ExtraArgs={"ContentType": content_type}
    )
    return s3_key

def add_image_to_property(property_id, s3_key, is_primary=False):
    """Links image to property via API"""
    payload = {
        "image_url": s3_key,
        "is_primary": is_primary,
        "sort_order": 0
    }
    resp = requests.post(f"{API_BASE}/properties/{property_id}/images", json=payload)
    if resp.status_code != 201:
        print(f"  ❌ Link Failed: {resp.text}")

def get_all_properties():
    print(f"  Fetching properties from {API_BASE}...")
    try:
        resp = requests.get(f"{API_BASE}/properties?limit=100")
        if resp.status_code != 200:
            print(f"  ❌ Failed to fetch properties: {resp.status_code} {resp.text}")
            return []
        data = resp.json()
        print(f"  ✅ Extracted {len(data)} properties.")
        # print([p['property_name'] for p in data]) # Debug list
        return data
    except Exception as e:
        print(f"  ❌ Connection Error: {e}")
        return []

def find_best_match(filename, properties):
    # Normalize filename: remove extension, lower case, strip
    name_search = os.path.splitext(os.path.basename(filename))[0].lower().strip()
    
    best_match = None
    best_ratio = 0.0
    
    for prop in properties:
        prop_name = prop['property_name'].lower().strip()
        
        # 1. Exact match
        if name_search == prop_name:
            return prop, 1.0
            
        # 2. Fuzzy match
        ratio = SequenceMatcher(None, name_search, prop_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = prop
            
    return best_match, best_ratio

def seed():
    images = [
        "/Users/maheswaranm/Downloads/Arcade Inn Coliving.jpg",
        "/Users/maheswaranm/Downloads/Avinya co live.jpg",
        "/Users/maheswaranm/Downloads/Co living Hub 0.2.jpg",
        "/Users/maheswaranm/Downloads/Connect coliving 2.jpg",
        "/Users/maheswaranm/Downloads/Pro colive (new).jpg",
        "/Users/maheswaranm/Downloads/DVR coliving.jpg",
        "/Users/maheswaranm/Downloads/Connect coliving.jpeg",
        "/Users/maheswaranm/Downloads/Shine premium colive.jpg",
        "/Users/maheswaranm/Downloads/Varadhi premium co living pg.jpg",
        "/Users/maheswaranm/Downloads/Urban living.jpg",
        "/Users/maheswaranm/Downloads/SGR enclave coliving.jpg",
        "/Users/maheswaranm/Downloads/Premium Urban Coliving.jpg",
        "/Users/maheswaranm/Downloads/kings & Queens Coliving.jpg",
        "/Users/maheswaranm/Downloads/Haveli Coliving.jpg",
        "/Users/maheswaranm/Downloads/Flock 9 Coliving.jpg",
        "/Users/maheswaranm/Downloads/Aveniya.jpeg",
        "/Users/maheswaranm/Downloads/dvr.jpeg",
        "/Users/maheswaranm/Downloads/Connect Coliving 2,.jpeg",
        "/Users/maheswaranm/Downloads/shine premium colive.jpeg",
        "/Users/maheswaranm/Downloads/hevenhome.jpeg",
        "/Users/maheswaranm/Downloads/Geet Co-Living.jpg",
        "/Users/maheswaranm/Downloads/Mr & Mrs coliving( Mahadevpura).jpg",
        "/Users/maheswaranm/Downloads/Mio Colive PG.jpg",
        "/Users/maheswaranm/Downloads/AA Premium Coliving PG.jpg",
        "/Users/maheswaranm/Downloads/JR LUXURY COLIVING.jpg",
        "/Users/maheswaranm/Downloads/Lakshya Co-Living PG.jpg",
        "/Users/maheswaranm/Downloads/K.N Co-living Pg.jpg",
        "/Users/maheswaranm/Downloads/Guest Inn Luxury PG for Gents.jpg",
        "/Users/maheswaranm/Downloads/Kio Colive PG.jpg",
        "/Users/maheswaranm/Downloads/Ashok PG Colive.jpg",
        "/Users/maheswaranm/Downloads/AA Epsilon Premium Colive.jpg",
        "/Users/maheswaranm/Downloads/Astro living.jpg",
        "/Users/maheswaranm/Downloads/Heaven coliving pg.jpg",
        "/Users/maheswaranm/Downloads/AA Sparrow Nest Colive.jpg",
        "/Users/maheswaranm/Downloads/Cozhy coliving pg.jpg",
        "/Users/maheswaranm/Downloads/Livingnest Falcon coliving.jpg",
        "/Users/maheswaranm/Downloads/Chap & dona coliving.jpg",
        "/Users/maheswaranm/Downloads/KOINN Coliving PG.jpg",
        "/Users/maheswaranm/Downloads/Gina Artize Bomasandra.jpg",
        "/Users/maheswaranm/Downloads/At Homes Permium co living pg.jpg",
        "/Users/maheswaranm/Downloads/Flechazo co living-PG.jpg",
        "/Users/maheswaranm/Downloads/AA Sparrow nest premium co live pg.jpg",
        "/Users/maheswaranm/Downloads/GVS Coliving Studio Rooms.jpg",
    ]
    
    if not BUCKET_NAME:
        print("❌ Error: S3_BUCKET_NAME not found in .env")
        return

    print("🚀 Starting Image Matching & Upload...")
    
    properties = get_all_properties()
    print(f"  Found {len(properties)} properties in DB.")
    
    if not properties:
        print("❌ No properties found to match against. Exiting.")
        return
        
    # force upload for Arcade Inn
    target_prop = next((p for p in properties if p['property_name'] == "Arcade Inn Coliving"), None)
    if target_prop:
        print(f"  Found Arcade Inn Coliving (ID: {target_prop['id']})")
        # Find the image
        img_path = "/Users/maheswaranm/Downloads/Arcade Inn Coliving.jpg"
        if os.path.exists(img_path):
            try:
                key = upload_image_to_s3(img_path)
                add_image_to_property(target_prop['id'], key, is_primary=True)
                print(f"  ✅ Force Linked Arcade Inn image: {key}")
            except Exception as e:
                print(f"  ❌ Error force linking: {e}")
        else:
            print(f"  ❌ Image not found: {img_path}")
            
    for img_path in images:
        if not os.path.exists(img_path):
            print(f"  ⚠️ File not found: {img_path}")
            continue
            
        match, score = find_best_match(img_path, properties)
        
        # 0.6 determines how 'fuzzy' we allow. 
        # Given the filenames are mostly accurate, 0.6 is safe.
        if match and score > 0.5: 
            fname = os.path.basename(img_path)
            print(f"  ✅ Matched '{fname}' \n     -> '{match['property_name']}' (Score: {score:.2f})")
            
            try:
                # Upload to S3
                key = upload_image_to_s3(img_path)
                
                # Link to DB
                # is_primary=True if unique image? 
                # Let's verify existing images count?
                # For now just add it.
                add_image_to_property(match['id'], key, is_primary=False) 
                print(f"     Linked Success!")
            except Exception as e:
                print(f"     ❌ Error: {e}")
        else:
            print(f"  ❌ No match for '{os.path.basename(img_path)}' (Score: {score:.2f})")

if __name__ == "__main__":
    seed()
