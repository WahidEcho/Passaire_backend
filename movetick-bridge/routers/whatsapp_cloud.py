import logging
import os

from fastapi import APIRouter, Request, Response
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp-cloud", tags=["whatsapp-cloud"])

VERIFY_TOKEN = os.getenv("WA_CLOUD_VERIFY_TOKEN")


@router.get("/webhook")
async def verify_webhook(request: Request):
    """
    Meta's one-time handshake when you click "Verify and save" in the
    App Dashboard. Must echo back hub.challenge if hub.verify_token matches.
    """
    params = request.query_params
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("[WA-Cloud] Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("[WA-Cloud] Webhook verification failed")
    return Response(status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Meta POSTs here for incoming messages, delivery/read status updates,
    template status changes, etc. Always return 200 quickly — errors
    are logged, never surfaced to Meta (they retry for up to 7 days
    on any non-200 response).
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            field = change.get("field")
            value = change.get("value", {})

            if field == "messages" and value.get("messages"):
                for msg in value["messages"]:
                    logger.info(
                        "[WA-Cloud] Incoming message from %s: %s",
                        msg.get("from"), msg.get("text", {}).get("body"),
                    )
            elif field == "messages" and value.get("statuses"):
                for status in value["statuses"]:
                    logger.info(
                        "[WA-Cloud] Status update: id=%s status=%s",
                        status.get("id"), status.get("status"),
                    )
            else:
                logger.info("[WA-Cloud] Webhook field=%s value=%s", field, value)

    return {"status": "ok"}
