import asyncio
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel
from dotenv import load_dotenv

from services.supabase_client import get_supabase
from services import whatsapp_cloud as wa_cloud_service

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp-cloud", tags=["whatsapp-cloud"])

VERIFY_TOKEN = os.getenv("WA_CLOUD_VERIFY_TOKEN")
APP_SECRET   = os.getenv("WA_CLOUD_APP_SECRET")

STATUS_MAP = {"sent": "sent", "delivered": "delivered", "read": "read", "failed": "failed"}


# ── Bulk send (admin-triggered, Cloud API requires an approved template) ──────

class BulkTemplateSendRequest(BaseModel):
    event_id: str
    template_name: str
    language: str = "en_US"
    body_params: list[str] | None = None   # each may use {name}/{event_name}/{event_date}/{venue}
    image_url: str | None = None


def _fill_params(params: list[str], guest: dict, event: dict) -> list[str]:
    return [
        p.replace("{name}", guest.get("name", ""))
         .replace("{event_name}", event.get("name", ""))
         .replace("{event_date}", str(event.get("date", "")))
         .replace("{venue}", event.get("venue") or "")
        for p in params
    ]


async def _send_bulk_template(guests: list[dict], event: dict, req: BulkTemplateSendRequest, message_type: str):
    sb = get_supabase()
    for i, guest in enumerate(guests):
        params = _fill_params(req.body_params or [], guest, event)
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            resp = await wa_cloud_service.send_template(
                to=guest["phone"], template_name=req.template_name,
                language=req.language, body_params=params, image_url=req.image_url,
            )
            msg_id = (resp.get("messages") or [{}])[0].get("id")
            sb.table("p_message_log").insert({
                "event_id": event["id"], "guest_id": guest["id"], "channel": "whatsapp",
                "message_type": message_type, "recipient": guest["phone"],
                "provider_message_id": msg_id, "status": "sent", "sent_at": now_iso,
            }).execute()
        except Exception as e:
            logger.error("[WA-Cloud] Bulk send failed for %s: %s", guest["phone"], e)
            sb.table("p_message_log").insert({
                "event_id": event["id"], "guest_id": guest["id"], "channel": "whatsapp",
                "message_type": message_type, "recipient": guest["phone"],
                "status": "failed", "error_detail": str(e)[:500], "failed_at": now_iso,
            }).execute()
        if i < len(guests) - 1:
            await asyncio.sleep(1.2)


@router.post("/send-invitations")
async def send_invitations_cloud(body: BulkTemplateSendRequest, background_tasks: BackgroundTasks):
    sb = get_supabase()
    event_res = sb.table("p_events").select("*").eq("id", body.event_id).limit(1).execute()
    if not event_res.data:
        raise HTTPException(404, "Event not found")
    event = event_res.data[0]

    guests = (
        sb.table("p_guests").select("*")
        .eq("event_id", body.event_id).eq("status", "invited").execute().data or []
    )
    if not guests:
        return {"message": "No invited guests to send to", "count": 0}
    background_tasks.add_task(_send_bulk_template, guests, event, body, "invitation")
    return {"message": f"Sending {len(guests)} invitations via WhatsApp Cloud API", "count": len(guests)}


@router.post("/send-reminder")
async def send_reminder_cloud(body: BulkTemplateSendRequest, background_tasks: BackgroundTasks):
    sb = get_supabase()
    event_res = sb.table("p_events").select("*").eq("id", body.event_id).limit(1).execute()
    if not event_res.data:
        raise HTTPException(404, "Event not found")
    event = event_res.data[0]

    guests = (
        sb.table("p_guests").select("*")
        .eq("event_id", body.event_id).eq("status", "confirmed").execute().data or []
    )
    if not guests:
        return {"message": "No confirmed guests to send to", "count": 0}
    background_tasks.add_task(_send_bulk_template, guests, event, body, "reminder")
    return {"message": f"Sending reminder to {len(guests)} confirmed guests via WhatsApp Cloud API", "count": len(guests)}


def _verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Verify Meta's X-Hub-Signature-256 header (HMAC-SHA256 over the raw
    request body, keyed with the Meta App Secret). Fails closed if the
    app secret isn't configured.
    """
    if not APP_SECRET:
        logger.error("[WA-Cloud] WA_CLOUD_APP_SECRET not set — rejecting webhook")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


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
    on any non-200 response). Signature-verified so a spoofed POST
    can't inject fake delivery status into p_message_log.
    """
    raw = await request.body()
    if not _verify_meta_signature(raw, request.headers.get("x-hub-signature-256")):
        logger.warning("[WA-Cloud] Webhook signature verification failed")
        raise HTTPException(401, "Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}

    sb = get_supabase()

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
                    wamid, wa_status = status.get("id"), status.get("status")
                    logger.info("[WA-Cloud] Status update: id=%s status=%s", wamid, wa_status)
                    new_status = STATUS_MAP.get(wa_status)
                    if not wamid or not new_status:
                        continue
                    now_iso = datetime.now(timezone.utc).isoformat()
                    update = {"status": new_status, "updated_at": now_iso}
                    if new_status == "delivered":
                        update["delivered_at"] = now_iso
                    elif new_status == "read":
                        update["read_at"] = now_iso
                    elif new_status == "failed":
                        update["failed_at"] = now_iso
                        errors = status.get("errors") or []
                        if errors:
                            update["error_detail"] = (errors[0].get("title") or errors[0].get("message") or "")[:500]
                    try:
                        sb.table("p_message_log").update(update).eq("provider_message_id", wamid).execute()
                    except Exception as e:
                        logger.error("[WA-Cloud] Failed to update message_log for %s: %s", wamid, e)
            else:
                logger.info("[WA-Cloud] Webhook field=%s value=%s", field, value)

    return {"status": "ok"}
