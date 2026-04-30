import boto3
import sys

def update_sg():
    access_key = "AKIAY6DIL2D7DYV2ECJI"
    secret_key = "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"
    region = "ap-south-1"
    group_id = "sg-076f2f31a3c41c6b7"
    current_ip = "171.76.82.80"

    print(f"Updating Security Group {group_id} to allow SSH from {current_ip}...")
    
    try:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        ec2 = session.client('ec2')
        
        ec2.authorize_security_group_ingress(
            GroupId=group_id,
            IpProtocol='tcp',
            FromPort=22,
            ToPort=22,
            CidrIp=f"{current_ip}/32"
        )
        print("✅ Successfully added your current IP to the Security Group.")
    except Exception as e:
        if 'InvalidPermission.Duplicate' in str(e):
            print("✅ Your IP is already whitelisted.")
        else:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    update_sg()
