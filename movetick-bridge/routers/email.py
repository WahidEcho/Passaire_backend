import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from svix.webhooks import Webhook, WebhookVerificationError

from services import resend_email
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email", tags=["email"])

RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET")
RESEND_STATUS_MAP = {
    "email.sent": "sent", "email.delivered": "delivered",
    "email.bounced": "bounced", "email.failed": "failed", "email.complained": "complained",
}


class TestEmailRequest(BaseModel):
    to: str


@router.post("/test")
async def send_test_email(body: TestEmailRequest):
    """
    Send a one-off test email via Resend to confirm the integration works.
    """
    html = """
    <div style="font-family:-apple-system,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <h2 style="color:#B8962E;">🎟️ Move Tick — Test Email</h2>
      <p>This is a test send confirming the Resend integration is wired up
      correctly for <strong>movetick@mbeg.org</strong>.</p>
      <p style="color:#888;font-size:13px;">If you received this, sending works.</p>
    </div>
    """
    try:
        result = await resend_email.send_email(
            to=body.to,
            subject="Move Tick — Resend Integration Test",
            html=html,
        )
    except Exception as e:
        logger.exception("Test email failed")
        raise HTTPException(500, detail=str(e))

    return {"sent": True, "resend_response": result}


# ── Bulk send to a guest list ───────────────────────────────────────────────────

class BulkEmailRequest(BaseModel):
    event_id: str
    subject: str
    html_template: str              # supports {name}/{event_name}/{event_date}/{venue}
    target_status: str = "invited"  # invited | confirmed | all
    message_type: str = "bulk"      # tag stored in p_message_log for the Delivery Log


async def _send_bulk_email(guests: list[dict], event: dict, subject_tpl: str, html_tpl: str, message_type: str):
    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    CHUNK = 100  # Resend batch endpoint limit
    for start in range(0, len(guests), CHUNK):
        chunk = guests[start:start + CHUNK]
        emails = [{
            "to": g["email"],
            "subject": subject_tpl.replace("{name}", g["name"]),
            "html": html_tpl.replace("{name}", g["name"])
                             .replace("{event_name}", event.get("name", ""))
                             .replace("{event_date}", str(event.get("date", "")))
                             .replace("{venue}", event.get("venue") or ""),
        } for g in chunk]
        try:
            result = await resend_email.send_batch(emails)
            ids = [item.get("id") for item in result.get("data", [])]
            rows = [{
                "event_id": event["id"], "guest_id": g["id"], "channel": "email",
                "message_type": message_type, "recipient": g["email"],
                "provider_message_id": mid, "status": "sent", "sent_at": now_iso,
            } for g, mid in zip(chunk, ids)]
        except Exception as e:
            logger.error("[Email] Batch send failed: %s", e)
            rows = [{
                "event_id": event["id"], "guest_id": g["id"], "channel": "email",
                "message_type": message_type, "recipient": g["email"],
                "status": "failed", "error_detail": str(e)[:500], "failed_at": now_iso,
            } for g in chunk]
        sb.table("p_message_log").insert(rows).execute()


@router.post("/send-bulk")
async def send_bulk_email(body: BulkEmailRequest, background_tasks: BackgroundTasks):
    sb = get_supabase()
    event_res = sb.table("p_events").select("*").eq("id", body.event_id).limit(1).execute()
    if not event_res.data:
        raise HTTPException(404, "Event not found")
    event = event_res.data[0]

    query = (
        sb.table("p_guests").select("*")
        .eq("event_id", body.event_id)
        .not_.is_("email", "null")
    )
    if body.target_status != "all":
        query = query.eq("status", body.target_status)
    guests = query.execute().data or []
    if not guests:
        return {"message": "No guests with an email address match this filter", "count": 0}

    background_tasks.add_task(_send_bulk_email, guests, event, body.subject, body.html_template, body.message_type)
    return {"message": f"Sending email to {len(guests)} guests", "count": len(guests)}


# ── Resend delivery-status webhook ──────────────────────────────────────────────

@router.post("/webhook")
async def resend_webhook(request: Request):
    """
    Resend POSTs here for email.sent/delivered/bounced/failed/complained
    events. Signature-verified (svix) so a spoofed POST can't inject fake
    delivery status into p_message_log. Fails closed if the signing
    secret isn't configured.
    """
    raw = await request.body()
    if not RESEND_WEBHOOK_SECRET:
        logger.error("[Resend] RESEND_WEBHOOK_SECRET not set — rejecting webhook")
        raise HTTPException(500, "Webhook not configured")

    headers = {
        "svix-id":        request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }
    try:
        Webhook(RESEND_WEBHOOK_SECRET).verify(raw, headers)
    except WebhookVerificationError:
        logger.warning("[Resend] Invalid webhook signature")
        raise HTTPException(401, "Invalid signature")

    payload = json.loads(raw)
    event_type, data = payload.get("type", ""), payload.get("data", {})
    email_id = data.get("email_id")
    new_status = RESEND_STATUS_MAP.get(event_type)
    logger.info("[Resend] event=%s email_id=%s", event_type, email_id)
    if not email_id or not new_status:
        return {"status": "ignored"}

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {"status": new_status, "updated_at": now_iso}
    if new_status == "delivered":
        update["delivered_at"] = now_iso
    elif new_status in ("bounced", "failed"):
        update["failed_at"] = now_iso
        bounce = data.get("bounce") or {}
        update["error_detail"] = (
            f"{bounce.get('type')}/{bounce.get('subType')}: {bounce.get('message')}"
            if bounce else str(data.get("reason") or "")[:500]
        )
    elif new_status == "complained":
        update["error_detail"] = "Recipient marked as spam"

    sb = get_supabase()
    try:
        sb.table("p_message_log").update(update).eq("provider_message_id", email_id).execute()
    except Exception as e:
        logger.error("[Resend] Failed to update message_log for %s: %s", email_id, e)
    return {"status": "ok"}
