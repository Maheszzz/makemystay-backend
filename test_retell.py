import asyncio
import httpx
from app.core.config import settings
from app.api.retell import trigger_outbound_call
import pytest

@pytest.mark.anyio
async def test_call():
    print(f"Key: {settings.RETELL_API_KEY}")
    print(f"Agent: {settings.RETELL_AGENT_ID}")
    print(f"From: {settings.RETELL_FROM_NUMBER}")
    payload = {
        "from_number": settings.RETELL_FROM_NUMBER,
        "to_number": "+919790341157",
        "agent_id": settings.RETELL_AGENT_ID,
        "metadata": {"test_id": 1},
        "retell_llm_dynamic_variables": {
            "name": "Test",
            "location": "",
            "property_type": "",
            "requirement": "interested in property options",
            "test_id": 1,
        },
    }
    url = "https://api.retellai.com/v2/create-phone-call"
    headers = {
        "Authorization": f"Bearer {settings.RETELL_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        print(resp.status_code)
        print(resp.text)

if __name__ == "__main__":
    asyncio.run(test_call())
