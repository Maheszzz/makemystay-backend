import boto3

def get_production_ips():
    session = boto3.Session(region_name='ap-south-1')
    ec2 = session.client('ec2')
    
    print("🔍 Searching for running 'makemystay' instances...")
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'instance-state-name', 'Values': ['running']},
            {'Name': 'tag:Name', 'Values': ['makemystay*']}
        ]
    )
    
    ips = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            ip = instance.get('PublicIpAddress')
            name = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
            if ip:
                print(f"✅ Found {name}: {ip}")
                ips.append(ip)
    
    return ips

if __name__ == "__main__":
    try:
        ips = get_production_ips()
        if not ips:
            print("❌ No matching instances found.")
        else:
            print("\n📋 Target IP List:")
            for ip in ips:
                print(ip)
    except Exception as e:
        print(f"❌ Error: {e}")
