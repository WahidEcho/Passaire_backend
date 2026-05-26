import os
import httpx
from dotenv import load_dotenv

load_dotenv()

INSTANCE_ID = os.getenv("GREENAPI_INSTANCE_ID")
TOKEN        = os.getenv("GREENAPI_TOKEN")
API_URL      = os.getenv("GREENAPI_API_URL", "https://7107.api.greenapi.com")


def _base() -> str:
    return f"{API_URL}/waInstance{INSTANCE_ID}"


async def send_text(phone: str, message: str) -> dict:
    """
    Send a plain-text WhatsApp message via Green API.
    phone must be in international format without +, e.g. 201039048775
    """
    chat_id = f"{phone}@c.us"
    url = f"{_base()}/sendMessage/{TOKEN}"
    payload = {"chatId": chat_id, "message": message}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()


async def send_image(phone: str, image_url: str, caption: str = "") -> dict:
    """
    Send an image from a public URL via Green API.
    Used to deliver QR ticket images.
    """
    chat_id = f"{phone}@c.us"
    url = f"{_base()}/sendFileByUrl/{TOKEN}"
    payload = {
        "chatId": chat_id,
        "urlFile": image_url,
        "fileName": "ticket.png",
        "caption": caption,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()


def set_webhook(webhook_url: str) -> dict:
    """
    Tell Green API where to POST incoming messages.
    Call this once after deployment via POST /setup-webhook.
    """
    url = f"{_base()}/setSettings/{TOKEN}"
    payload = {
        "webhookUrl": webhook_url,
        "incomingWebhook": "yes",
        "outgoingWebhook": "no",
        "outgoingMessageWebhook": "no",
    }
    r = httpx.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()
