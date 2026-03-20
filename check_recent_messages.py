import os
from twilio.rest import Client

def main():
    account_sid = os.environ.get('TWILIO_ACCOUNT_SID', 'AC4c361075204c05d9c6bcabaf62a76696')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN', '8ada166ab54eb825569b9851591b9850')
    client = Client(account_sid, auth_token)
    
    messages = client.messages.list(limit=5)
    for msg in messages:
        print(f"Time: {msg.date_sent}, To: {msg.to}, Status: {msg.status}, Body: {msg.body[:50]}")

if __name__ == "__main__":
    main()
