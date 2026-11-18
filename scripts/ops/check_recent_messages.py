import os
import sys
from pathlib import Path

from twilio.rest import Client

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.config import load_app_env  # noqa: E402

load_app_env()


def main():
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()

    if not account_sid or not auth_token:
        print("Error: TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    client = Client(account_sid, auth_token)
    messages = client.messages.list(limit=5)
    for msg in messages:
        print(f"Time: {msg.date_sent}, To: {msg.to}, Status: {msg.status}, Body: {(msg.body or '')[:50]}")


if __name__ == "__main__":
    main()
