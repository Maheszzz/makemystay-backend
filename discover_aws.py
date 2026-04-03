import boto3
import json

def discover():
    session = boto3.Session(region_name='ap-south-1')
    
    elbv2 = session.client('elbv2')
    ec2 = session.client('ec2')
    
    print("--- Target Groups ---")
    tgs = elbv2.describe_target_groups()
    for tg in tgs['TargetGroups']:
        tg_arn = tg['TargetGroupArn']
        tg_name = tg['TargetGroupName']
        print(f"\nGroup: {tg_name}")
        print(f"ARN: {tg_arn}")
        
        health = elbv2.describe_target_health(TargetGroupArn=tg_arn)
        instance_ids = []
        for target in health['TargetHealthDescriptions']:
            target_id = target['Target']['Id']
            state = target['TargetHealth']['State']
            print(f"  - Target: {target_id} (State: {state})")
            if state == 'healthy':
                instance_ids.append(target_id)
        
        if instance_ids:
            print("  --- Public IPs ---")
            instances = ec2.describe_instances(InstanceIds=instance_ids)
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    ip = instance.get('PublicIpAddress', 'N/A')
                    name = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    print(f"    - {name}: {ip} (ID: {instance['InstanceId']})")

if __name__ == "__main__":
    try:
        discover()
    except Exception as e:
        print(f"Error: {e}")
