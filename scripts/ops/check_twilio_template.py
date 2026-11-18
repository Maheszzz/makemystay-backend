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
    template_sid = os.environ.get("TWILIO_WHATSAPP_TEMPLATE_SID", "").strip()

    if not account_sid or not auth_token or not template_sid:
        print(
            "Error: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_TEMPLATE_SID must be set.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = Client(account_sid, auth_token)
    try:
        content = client.content.v1.contents(template_sid).fetch()
        print("Variables expected:", content.variables)
        print("Types:", content.types)
    except Exception as e:
        print("Error fetching content:", e)


if __name__ == "__main__":
    main()
