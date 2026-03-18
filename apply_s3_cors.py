import boto3
import json
import os
from dotenv import load_dotenv

# Load credentials from .env.production
load_dotenv('.env.production')

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')
BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'makemystayrealty')

print(f"Applying CORS to bucket: {BUCKET_NAME} in region: {AWS_REGION}")

s3 = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

cors_configuration = {
    'CORSRules': [
        {
            'AllowedHeaders': ['*'],
            'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
            'AllowedOrigins': [
                'http://localhost:5173',
                'http://localhost:3000',
                'https://makemystay.ai',
                'https://www.makemystay.ai',
                'https://admin.makemystay.ai'
            ],
            'ExposeHeaders': ['ETag', 'Content-Type'],
            'MaxAgeSeconds': 3000
        }
    ]
}

try:
    s3.put_bucket_cors(Bucket=BUCKET_NAME, CORSConfiguration=cors_configuration)
    print("Successfully applied CORS configuration!")
except Exception as e:
    print(f"Error applying CORS: {e}")
