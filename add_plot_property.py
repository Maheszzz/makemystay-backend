import requests
import boto3
import os
import mimetypes
from dotenv import load_dotenv

load_dotenv()

API_BASE = "http://127.0.0.1:8000/api/v1/realty"
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

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
    
    print(f"☁️ Uploading {filename} to S3...")
    s3.upload_file(
        filepath, 
        BUCKET_NAME, 
        s3_key, 
        ExtraArgs={"ContentType": content_type}
    )
    return s3_key

def add_plot_property():
    print("🏠 Creating new plot property...")
    plot_data = {
        "property_name": "Premium Residential Plot",
        "location": "Upcoming Development Area",
        "starting_price": 4500000.0,
        "property_type": "Plot",
        "listing_type": "buy",
        "phone": "9999999999",
        "description": "Excellent investment opportunity. Prime residential plot available for sale."
    }
    
    headers = {"Content-Type": "application/json"}
    response = requests.post(f"{API_BASE}/properties", headers=headers, json=plot_data)
    
    if response.status_code in [200, 201]:
        prop = response.json()
        print(f"✅ Success! Created property ID: {prop.get('id')}")
        return prop.get('id')
    else:
        print(f"❌ Failed to create property. Status: {response.status_code}")
        print(response.text)
        return None

def add_image_to_property(property_id, s3_key, is_primary=True):
    """Links image to property via API"""
    print(f"🔗 Linking S3 image to property ID {property_id}...")
    payload = {
        "image_url": s3_key,
        "is_primary": is_primary,
        "sort_order": 0
    }
    resp = requests.post(f"{API_BASE}/properties/{property_id}/images", json=payload)
    if resp.status_code == 201:
        print("✅ Image successfully linked!")
    else:
        print(f"❌ Link Failed: {resp.text}")

def main():
    img_path = "/Users/maheswaranm/Downloads/Plot_sale.png"
    
    if not os.path.exists(img_path):
        print(f"❌ Error: Image file not found at {img_path}")
        return
        
    # 1. Create property
    prop_id = add_plot_property()
    if not prop_id:
        return
        
    # 2. Upload image
    try:
        s3_key = upload_image_to_s3(img_path)
        print(f"✅ Uploaded to S3 Key: {s3_key}")
        
        # 3. Link image
        add_image_to_property(prop_id, s3_key)
        
    except Exception as e:
        print(f"❌ Error during S3 upload or linking: {str(e)}")

if __name__ == "__main__":
    main()
