import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY    = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "movetick@mbeg.org")
FROM_NAME  = os.getenv("RESEND_FROM_NAME", "Move Tick")
API_URL    = "https://api.resend.com"


def _from_header() -> str:
    return f"{FROM_NAME} <{FROM_EMAIL}>"


async def send_email(to: str, subject: str, html: str, reply_to: str | None = None) -> dict:
    """
    Send a single transactional email via Resend.
    """
    payload = {
        "from":    _from_header(),
        "to":      [to],
        "subject": subject,
        "html":    html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{API_URL}/emails",
            json=payload,
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        r.raise_for_status()
        return r.json()


async def send_batch(emails: list[dict]) -> dict:
    """
    Send up to 100 emails in one call via Resend's batch endpoint.
    Each item: {"to": str, "subject": str, "html": str}
    """
    payload = [
        {
            "from":    _from_header(),
            "to":      [e["to"]],
            "subject": e["subject"],
            "html":    e["html"],
        }
        for e in emails
    ]
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{API_URL}/emails/batch",
            json=payload,
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        r.raise_for_status()
        return r.json()
