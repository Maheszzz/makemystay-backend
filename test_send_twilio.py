import os
import json
from twilio.rest import Client

def main():
    account_sid = os.environ.get('TWILIO_ACCOUNT_SID', 'AC4c361075204c05d9c6bcabaf62a76696')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN', '8ada166ab54eb825569b9851591b9850')
    from_value = 'whatsapp:+919187201191'
    to_value = 'whatsapp:+919790341157'
    sid = 'HXde1735ecfbb5ce15a9493592d204e225'
    
    client = Client(account_sid, auth_token)
    
    try:
        print("Testing with JSON string...")
        msg = client.messages.create(
            from_=from_value,
            to=to_value,
            content_sid=sid,
            content_variables=json.dumps({"1": "Mahesh", "2": "Bangalore", "3": "50 Lakhs"})
        )
        print("Success! SID:", msg.sid)
    except Exception as e:
        print("Failed with JSON string:", e)
        
    try:
        print("\nTesting with raw dictionary (letting twilio-python serialize it)...")
        msg = client.messages.create(
            from_=from_value,
            to=to_value,
            content_sid=sid,
            content_variables={"1": "Mahesh", "2": "Bangalore", "3": "50 Lakhs"}
        )
        print("Success! SID:", msg.sid)
    except Exception as e:
        print("Failed with raw dictionary:", e)

if __name__ == "__main__":
    main()
