import os
from twilio.rest import Client
from loguru import logger
import json

def main():
    account_sid = os.environ.get('TWILIO_ACCOUNT_SID', 'AC4c361075204c05d9c6bcabaf62a76696')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN', '8ada166ab54eb825569b9851591b9850')
    client = Client(account_sid, auth_token)
    try:
        content = client.content.v1.contents('HXde1735ecfbb5ce15a9493592d204e225').fetch()
        print("Variables expected:", content.variables)
        print("Types:", content.types)
    except Exception as e:
        print("Error fetching content:", e)

if __name__ == "__main__":
    main()
