import boto3
import sys
import os
from dotenv import load_dotenv

# Load production env
env_path = os.path.join(os.getcwd(), '.env.production')
load_dotenv(env_path)

def test_s3_connection():
    bucket_name = os.getenv('S3_BUCKET_NAME', 'makemystayrealty')
    key_id = os.getenv('AWS_ACCESS_KEY_ID')
    secret = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION', 'ap-south-1')

    print(f"🔍 Testing S3 Connection to bucket: {bucket_name}")
    print(f"📍 Region: {region}")

    if key_id:
        print(f"🔑 Key ID: {key_id[:8]}... (mask)")
    else:
        print("👤 Identity: Credential-less (Using IAM Instance Profile)")

    try:
        if key_id and secret:
            s3 = boto3.client(
                's3',
                aws_access_key_id=key_id,
                aws_secret_access_key=secret,
                region_name=region
            )
        else:
            s3 = boto3.client('s3', region_name=region)
        
        # 1. Test ListObjects
        print("  -> Attempting to list objects...")
        s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
        print("  ✅ ListObjects: Success")

        # 2. Test PutObject (Dry run with a temp file)
        test_key = "system-tests/connection-test.txt"
        print(f"  -> Attempting to put test object: {test_key}...")
        s3.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body="connection test",
            ContentType="text/plain"
        )
        print("  ✅ PutObject: Success")

        # 3. Clean up
        s3.delete_object(Bucket=bucket_name, Key=test_key)
        print("  ✅ DeleteObject: Success")
        
        print("\n🎉 S3 Credentials and Permissions are CORRECT.")

    except Exception as e:
        print(f"\n❌ S3 Audit FAILED: {e}")
        if "AccessDenied" in str(e):
            print("👉 Recommendation: Check IAM policy for the user. It needs s3:PutObject and s3:ListBucket.")
        elif "InvalidAccessKeyId" in str(e):
            print("👉 Recommendation: The AWS_ACCESS_KEY_ID is invalid.")
        elif "SignatureDoesNotMatch" in str(e):
            print("👉 Recommendation: The AWS_SECRET_ACCESS_KEY is incorrect.")

if __name__ == "__main__":
    test_s3_connection()
