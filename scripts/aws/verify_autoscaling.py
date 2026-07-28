import csv
import boto3
import json
import sys
from typing import Dict, List, Any

def get_credentials(csv_path: str) -> Dict[str, str]:
    try:
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            row = next(reader)
            return {
                'access_key': row[0].strip(),
                'secret_key': row[1].strip()
            }
    except Exception as e:
        print(f"Error loading credentials: {e}")
        sys.exit(1)

def verify_autoscaling():
    # 1. Credentials
    csv_path = '/Users/maheswaranm/Downloads/makemystay-backend_accessKeys.csv'
    creds = get_credentials(csv_path)

    # 2. Setup AWS Clients
    session = boto3.Session(
        aws_access_key_id=creds['access_key'],
        aws_secret_access_key=creds['secret_key'],
        region_name='ap-south-1'
    )
    
    ec2 = session.client('ec2')
    asg = session.client('autoscaling')
    elbv2 = session.client('elbv2')

    print("🔍 Beginning Layer 5 Verification (Auto Scaling & HA)...")
    print("-" * 50)

    # 3. Identify ASG
    asg_groups = asg.describe_auto_scaling_groups()['AutoScalingGroups']
    target_asg = None
    for group in asg_groups:
        if "makemystay" in group['AutoScalingGroupName'].lower():
            target_asg = group
            break
    
    if not target_asg:
        print("❌ Error: No Auto Scaling Group found matching 'makemystay'.")
        return

    name = target_asg['AutoScalingGroupName']
    print(f"✅ Found ASG: {name}")
    print(f"   Desired: {target_asg['DesiredCapacity']} | Min: {target_asg['MinSize']} | Max: {target_asg['MaxSize']}")
    
    # Check Multi-Instance / Multi-AZ
    subnets = target_asg['VPCZoneIdentifier'].split(',')
    print(f"   Subnets: {len(subnets)} {'(Multi-AZ ✅)' if len(subnets) >= 2 else '(Single AZ ⚠️)'}")
    
    if target_asg['DesiredCapacity'] < 2:
        print("   Status: ⚠️ Single Instance Mode (Not HA)")
    else:
        print("   Status: ✅ Multi-Instance Mode (High Availability)")

    # 4. Check Launch Template
    lt_spec = target_asg.get('LaunchTemplate') or target_asg.get('MixedInstancesPolicy', {}).get('LaunchTemplate', {}).get('LaunchTemplateSpecification')
    if lt_spec:
        lt_id = lt_spec['LaunchTemplateId']
        lt_versions = ec2.describe_launch_template_versions(LaunchTemplateId=lt_id)['LaunchTemplateVersions']
        latest = next(v for v in lt_versions if v['LatestVersion'])
        
        print(f"✅ Launch Template: {lt_id}")
        print(f"   Latest Version: {latest['VersionNumber']}")
        
        # Verify UserData contains the new boot sequence (pm2 resurrect)
        user_data = latest.get('LaunchTemplateData', {}).get('UserData', '')
        # Un-encode to check
        import base64
        decoded = base64.b64decode(user_data).decode('utf-8') if user_data else ""
        if "pm2 resurrect" in decoded:
            print("   Boot Sequence: ✅ PM2-based (Correct)")
        elif "docker run" in decoded:
            print("   Boot Sequence: ⚠️ Docker-based (Legacy/Broken)")
        else:
            print("   Boot Sequence: ❓ Unknown content")

    # 5. Check Load Balancer & Health Check
    tgs = elbv2.describe_target_groups()['TargetGroups']
    target_tg = None
    for tg in tgs:
        if "makemystay" in tg['TargetGroupName'].lower():
            target_tg = tg
            break
    
    if target_tg:
        print(f"✅ Load Balancer Target Group: {target_tg['TargetGroupName']}")
        print(f"   Health Check Path: {target_tg['HealthCheckPath']} {'(Correct ✅)' if target_tg['HealthCheckPath'] == '/health' else '(Incorrect ⚠️)'}")
        print(f"   Protocol: {target_tg['Protocol']} | Port: {target_tg['Port']}")
        
        # Check Health Status
        health = elbv2.describe_target_health(TargetGroupArn=target_tg['TargetGroupArn'])['TargetHealthDescriptions']
        healthy_count = sum(1 for h in health if h['TargetHealth']['State'] == 'healthy')
        print(f"   Healthy Instances: {healthy_count}/{len(health)}")
    else:
        print("⚠️ Warning: No Target Group found matching 'makemystay'.")

    print("-" * 50)
    print("🏁 Verification Complete.")

if __name__ == "__main__":
    verify_autoscaling()
