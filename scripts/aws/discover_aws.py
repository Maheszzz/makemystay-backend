import os
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.config import load_app_env  # noqa: E402

load_app_env()

def discover_instances():
    # Use environment variables if present
    session = boto3.Session(
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'ap-south-1')
    )
    ec2 = session.client('ec2')
    
    # Filter for instances with 'makemystay' in the Name tag
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:Name', 'Values': ['*makemystay*']}
        ]
    )
    
    print(f"{'Name':<25} | {'Instance ID':<20} | {'State':<15} | {'Public IP':<15}")
    print("-" * 85)
    
    found = False
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            name = "N/A"
            for tag in instance.get('Tags', []):
                if tag['Key'] == 'Name':
                    name = tag['Value']
            
            instance_id = instance['InstanceId']
            state = instance['State']['Name']
            public_ip = instance.get('PublicIpAddress', 'N/A')
            
            print(f"{name:<25} | {instance_id:<20} | {state:<15} | {public_ip:<15}")
            found = True
            
    if not found:
        print("No matches found for 'makemystay' in tags.")

if __name__ == "__main__":
    try:
        discover_instances()
    except Exception as e:
        print(f"Error connecting to AWS: {e}")
        print("Please ensure your AWS credentials (~/.aws/credentials) are configured correctly.")
