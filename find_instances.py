import boto3
import sys

def find_instances():
    access_key = "AKIAY6DIL2D7OWCXNI7G"
    secret_key = "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"
    region = "ap-south-1"

    try:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        elbv2 = session.client('elbv2')
        ec2 = session.client('ec2')

        print("🔍 Checking target groups...")
        tgs = elbv2.describe_target_groups()['TargetGroups']
        target_tg = None
        for tg in tgs:
            if "makemystay" in tg['TargetGroupName'].lower():
                target_tg = tg
                break
        
        if not target_tg:
            print("❌ No target group found.")
            return

        print(f"✅ Found TG: {target_tg['TargetGroupName']}")
        print(f"   Health Check Path: {target_tg['HealthCheckPath']}")

        health = elbv2.describe_target_health(TargetGroupArn=target_tg['TargetGroupArn'])['TargetHealthDescriptions']
        
        if not health:
            print("❌ No instances in target group.")
            return

        for h in health:
            instance_id = h['Target']['Id']
            state = h['TargetHealth']['State']
            reason = h['TargetHealth'].get('Reason', 'N/A')
            desc = h['TargetHealth'].get('Description', 'N/A')
            
            print(f"\n   Instance: {instance_id}")
            print(f"   State: {state}")
            if state != 'healthy':
                print(f"   Reason: {reason}")
                print(f"   Description: {desc}")

            # Get Public IP
            instances = ec2.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances']
            ip = instances[0].get('PublicIpAddress', 'No Public IP')
            print(f"   Public IP: {ip}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    find_instances()
