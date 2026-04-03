import boto3
import sys

def check_s3_cors(bucket_name):
    s3 = boto3.client('s3')
    try:
        response = s3.get_bucket_cors(Bucket=bucket_name)
        print(f"✅ CORS Configuration for {bucket_name}:")
        for rule in response.get('CORSRules', []):
            print(f"  - Allowed Origins: {rule.get('AllowedOrigins')}")
            print(f"  - Allowed Methods: {rule.get('AllowedMethods')}")
            print(f"  - Allowed Headers: {rule.get('AllowedHeaders')}")
            print(f"  - Expose Headers: {rule.get('ExposeHeaders')}")
    except Exception as e:
        print(f"❌ Error fetching CORS: {e}")
        print("Tip: If you get AccessDenied, ensure your IAM User/Role has 's3:GetBucketCors' permission.")

if __name__ == "__main__":
    bucket = "makemystay-in" # Primary bucket
    check_s3_cors(bucket)
