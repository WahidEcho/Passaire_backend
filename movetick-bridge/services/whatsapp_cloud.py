import os
import httpx
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN   = os.getenv("WA_CLOUD_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("WA_CLOUD_PHONE_NUMBER_ID")
API_VERSION    = os.getenv("WA_CLOUD_API_VERSION", "v21.0")
API_URL        = f"https://graph.facebook.com/{API_VERSION}"


def _headers() -> dict:
    return {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}


async def send_template(to: str, template_name: str, language: str = "en_US",
                         body_params: list[str] | None = None,
                         image_url: str | None = None) -> dict:
    """
    Send an approved message template. `to` must be in international
    format without +, e.g. 201039025839.
    """
    components = []
    if image_url:
        components.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"link": image_url}}],
        })
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in body_params],
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": components,
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API_URL}/{PHONE_NUMBER_ID}/messages", json=payload, headers=_headers())
        r.raise_for_status()
        return r.json()


async def send_text(to: str, message: str) -> dict:
    """
    Free-form text — only deliverable within a 24h customer-initiated
    conversation window. Use send_template() outside that window.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API_URL}/{PHONE_NUMBER_ID}/messages", json=payload, headers=_headers())
        r.raise_for_status()
        return r.json()
