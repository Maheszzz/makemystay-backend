import boto3

def test_keys(access_key, secret_key):
    try:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="ap-south-1"
        )
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        print(f"✅ Success! Identity: {identity['Arn']}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    print("Testing Key Set 1 (AKIA...NI7G):")
    test_keys("AKIAY6DIL2D7OWCXNI7G", "74w4JvH/x1W0l4QQkEY59yMOAGZ3WWODi3EL3Ugs")
    print("\nTesting Key Set 2 (AKIA...UVVI):")
    test_keys("AKIAY6DIL2D7CDFDUVVI", "IORi1DqQptxH5DkCL0WH80T54T96iZOU0E1BFAnv")
