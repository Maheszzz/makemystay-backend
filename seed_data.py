import requests
import boto3
import os
import mimetypes
from dotenv import load_dotenv
from difflib import SequenceMatcher
import glob

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
    # Normalize helper
    def normalize(s):
        # Replace common separators with space, remove unwanted chars
        return s.lower().replace('-', ' ').replace('_', ' ').replace(',', '').strip()

    # Normalize filename: remove extension
    fname_norm = normalize(os.path.splitext(os.path.basename(filename))[0])
    f_tokens = fname_norm.split()
    
    best_match = None
    best_ratio = 0.0
    
    for prop in properties:
        prop_name_orig = prop['property_name']
        prop_name_norm = normalize(prop_name_orig)
        p_tokens = prop_name_norm.split()
        
        # Base fuzzy match ratio
        ratio = SequenceMatcher(None, fname_norm, prop_name_norm).ratio()
        
        # Boost if first word matches (e.g. "dvr" == "dvr")
        if f_tokens and p_tokens and f_tokens[0] == p_tokens[0]:
            ratio += 0.3
            
        # Boost if whole filename is a prefix of property name
        if prop_name_norm.startswith(fname_norm):
             ratio += 0.2
            
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = prop
            
    return best_match, best_ratio

def seed():
    # Dynamic image loading
    img_dir = '/Users/maheswaranm/Makemystayrealty/properties-photos'
    if not os.path.exists(img_dir):
        print(f"❌ Error: Image directory not found: {img_dir}")
        return

    # Get all jpg/jpeg/png files
    extensions = ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG']
    images = []
    for ext in extensions:
        images.extend(glob.glob(os.path.join(img_dir, ext)))
    
    # Remove duplicates if any (e.g. case sensitivity issues)
    images = sorted(list(set(images)))
    
    print(f"  Found {len(images)} images in {img_dir}")
    
    if not BUCKET_NAME:
        print("❌ Error: S3_BUCKET_NAME not found in .env")
        return

    print("🚀 Starting Image Matching & Upload...")
    
    properties = get_all_properties()
    print(f"  Found {len(properties)} properties in DB.")
    
    if not properties:
        print("❌ No properties found to match against. Exiting.")
        return
        
    # Remove Force Linked Arcade Inn block since it's now in the list
            
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
                
                # Link to DB (Backend handles deduplication now)
                add_image_to_property(match['id'], key, is_primary=False) 
                print("     Linked Success!")
            except Exception as e:
                print(f"     ❌ Error: {e}")
        else:
            print(f"  ❌ No match for '{os.path.basename(img_path)}' (Score: {score:.2f})")

if __name__ == "__main__":
    seed()
