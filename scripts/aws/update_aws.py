import csv
import base64
import boto3
import time

def main():
    # 1. Load keys from CSV
    csv_path = '/Users/maheswaranm/Downloads/makemystay-backend_accessKeys.csv'
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        row = next(reader)
        access_key = row[0].strip()
        secret_key = row[1].strip()

    # 2. Setup AWS Clients
    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='ap-south-1'
    )
    sts = session.client('sts')
    ec2 = session.client('ec2')
    autoscaling = session.client('autoscaling')

    # 3. Get Account ID
    account_id = sts.get_caller_identity()['Account']
    print(f"Authenticated as Account ID: {account_id}")

    # 4. Update aws-user-data.sh with real Account ID
    user_data_file = '/Users/maheswaranm/no-broker-backend/aws-user-data.sh'
    with open(user_data_file, 'r') as f:
        user_data = f.read()
    
    # Replace placeholder
    user_data = user_data.replace('YOUR_ACCOUNT_ID', account_id)
    
    # Encode Base64
    user_data_b64 = base64.b64encode(user_data.encode('utf-8')).decode('utf-8')

    # 5. Find Auto Scaling Group that uses the template (or just trigger if known)
    # The template ID from the screenshot is lt-0a0ab85a84ed5a405
    lt_id = "lt-0a0ab85a84ed5a405"
    
    print(f"Creating new Launch Template Version for {lt_id}...")
    response = ec2.create_launch_template_version(
        LaunchTemplateId=lt_id,
        SourceVersion="$Latest",
        LaunchTemplateData={
            'UserData': user_data_b64
        }
    )
    new_version_number = response['LaunchTemplateVersion']['VersionNumber']
    print(f"Created new Version: {new_version_number}")

    # 6. Set as Default Version
    ec2.modify_launch_template(
        LaunchTemplateId=lt_id,
        DefaultVersion=str(new_version_number)
    )
    print(f"Set Default Version to {new_version_number}")

    # 7. Find Auto Scaling Group
    asg_response = autoscaling.describe_auto_scaling_groups()
    target_asg_name = None
    for group in asg_response['AutoScalingGroups']:
        if 'LaunchTemplate' in group and group['LaunchTemplate']['LaunchTemplateId'] == lt_id:
            target_asg_name = group['AutoScalingGroupName']
            break
        elif 'MixedInstancesPolicy' in group:
            lt = group['MixedInstancesPolicy']['LaunchTemplate']['LaunchTemplateSpecification']
            if lt['LaunchTemplateId'] == lt_id:
                target_asg_name = group['AutoScalingGroupName']
                break
    
    if not target_asg_name:
        # Fallback to name search
        for group in asg_response['AutoScalingGroups']:
            if "makemystay" in group['AutoScalingGroupName'].lower():
                target_asg_name = group['AutoScalingGroupName']
                break

    if target_asg_name:
        print(f"Found Target ASG: {target_asg_name}")
        
        # Ensure the ASG is pointing to $Default version (if it specifies an exact version, update it)
        autoscaling.update_auto_scaling_group(
            AutoScalingGroupName=target_asg_name,
            LaunchTemplate={
                'LaunchTemplateId': lt_id,
                'Version': '$Default'
            }
        )

        print(f"Triggering Instance Refresh on {target_asg_name}...")
        try:
            refresh_resp = autoscaling.start_instance_refresh(
                AutoScalingGroupName=target_asg_name,
                Strategy='Rolling',
                Preferences={
                    'MinHealthyPercentage': 50,
                    'InstanceWarmup': 60
                }
            )
            print(f"Successfully triggered Instance Refresh: {refresh_resp['InstanceRefreshId']}")
        except Exception as e:
            print(f"Failed to start instance refresh: {e}")
    else:
        print("Warning: Could not automatically locate the Auto Scaling Group linked to this Launch Template.")

if __name__ == "__main__":
    main()
