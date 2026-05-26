import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel

from services.supabase_client import get_supabase
from services import greenapi
from services.qr_generator import create_ticket_qr

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# ── Message Templates ────────────────────────────────────────────────────────

INVITATION_MSG = """🎟️ *{event_name}*

Hello {name}! You're invited to *{event_name}*.

📅 Date: {event_date}
📍 Venue: {venue}

To *confirm your attendance* and receive your entry ticket, reply *1*
To decline, reply *2*

See you there! 🎉"""

TICKET_MSG = """✅ *Your ticket is confirmed!*

Welcome, *{name}*!

Your QR code ticket for *{event_name}* is attached below.
Please show this at the gate on entry.

See you on {event_date}! 🎉"""

ALREADY_CONFIRMED_MSG = """You've already confirmed! Here's your ticket again 🎟️"""

DECLINE_MSG = """No problem, {name}! We've noted your response. Hope to see you at future events! 👋"""

INVALID_MSG = """Please reply *1* to confirm your attendance or *2* to decline."""


# ── Bulk Send ────────────────────────────────────────────────────────────────

class BulkSendRequest(BaseModel):
    event_id: str


async def _send_invitation_to_guest(guest: dict, event: dict):
    """Send invitation message to a single guest."""
    msg = INVITATION_MSG.format(
        name=guest["name"],
        event_name=event["name"],
        event_date=event["date"],
        venue=event.get("venue", "TBA"),
    )
    try:
        await greenapi.send_text(guest["phone"], msg)
        sb = get_supabase()
        sb.table("p_wa_messages").insert({
            "phone": guest["phone"],
            "message_type": "invitation",
            "status": "sent",
        }).execute()
    except Exception as e:
        logger.error("[WA] Failed to send invitation to %s: %s", guest["phone"], e)


@router.post("/send-invitations")
async def send_invitations(body: BulkSendRequest, background_tasks: BackgroundTasks):
    """
    Send WhatsApp invitations to all guests with status 'invited'.
    Runs in the background with 1.2 s delay between messages to avoid spam detection.
    """
    sb = get_supabase()

    event_res = sb.table("p_events").select("*").eq("id", body.event_id).single().execute()
    if not event_res.data:
        raise HTTPException(404, "Event not found")
    event = event_res.data

    guests_res = (
        sb.table("p_guests")
        .select("*")
        .eq("event_id", body.event_id)
        .eq("status", "invited")
        .execute()
    )
    guests = guests_res.data

    if not guests:
        return {"message": "No invited guests to send to", "count": 0}

    async def bulk_task():
        for i, guest in enumerate(guests):
            await _send_invitation_to_guest(guest, event)
            if i < len(guests) - 1:
                await asyncio.sleep(1.2)
        logger.info("[WA] Bulk send complete: %d invitations sent", len(guests))

    background_tasks.add_task(bulk_task)
    return {"message": f"Sending {len(guests)} invitations in background", "count": len(guests)}


# ── Bulk Reminder ────────────────────────────────────────────────────────────

class ReminderRequest(BaseModel):
    event_id: str
    message: str   # Free-form (use {name} for personalisation)


@router.post("/send-reminder")
async def send_reminder(body: ReminderRequest, background_tasks: BackgroundTasks):
    """Send a custom message to all confirmed guests."""
    sb = get_supabase()

    guests_res = (
        sb.table("p_guests")
        .select("*")
        .eq("event_id", body.event_id)
        .eq("status", "confirmed")
        .execute()
    )
    guests = guests_res.data

    if not guests:
        return {"message": "No confirmed guests found", "count": 0}

    async def reminder_task():
        for i, guest in enumerate(guests):
            personalised = body.message.replace("{name}", guest["name"])
            try:
                await greenapi.send_text(guest["phone"], personalised)
                sb.table("p_wa_messages").insert({
                    "phone": guest["phone"],
                    "message_type": "reminder",
                    "status": "sent",
                }).execute()
            except Exception as e:
                logger.error("[WA] Reminder failed for %s: %s", guest["phone"], e)
            if i < len(guests) - 1:
                await asyncio.sleep(1.2)

    background_tasks.add_task(reminder_task)
    return {"message": f"Sending reminder to {len(guests)} confirmed guests", "count": len(guests)}


# ── Webhook Handler ──────────────────────────────────────────────────────────

async def _handle_confirmation(guest: dict, event: dict, replied_yes: bool):
    sb = get_supabase()

    if not replied_yes:
        # Guest declined
        sb.table("p_guests").update({"status": "declined"}).eq("id", guest["id"]).execute()
        await greenapi.send_text(
            guest["phone"],
            DECLINE_MSG.format(name=guest["name"])
        )
        return

    # Guest confirmed — check if ticket already exists
    existing = (
        sb.table("p_tickets")
        .select("*")
        .eq("guest_id", guest["id"])
        .execute()
    )

    if existing.data:
        # Already has ticket — resend it
        ticket = existing.data[0]
        await greenapi.send_text(guest["phone"], ALREADY_CONFIRMED_MSG)
        await greenapi.send_image(
            guest["phone"],
            ticket["qr_image_url"],
            caption=f"Your ticket for {event['name']}",
        )
        return

    # New confirmation — generate & upload QR ticket
    try:
        token, qr_url = create_ticket_qr(
            guest_id=guest["id"],
            event_id=event["id"],
            guest_name=guest["name"],
            event_name=event["name"],
        )
    except Exception as exc:
        logger.error("[QR] Failed to generate ticket for guest %s: %s", guest["id"], exc)
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    sb.table("p_guests").update({"status": "confirmed"}).eq("id", guest["id"]).execute()

    sb.table("p_tickets").insert({
        "guest_id":    guest["id"],
        "event_id":    event["id"],
        "token":       token,
        "qr_image_url": qr_url,
        "sent_at":     now_iso,
    }).execute()

    sb.table("p_wa_messages").insert({
        "phone":        guest["phone"],
        "message_type": "ticket",
        "status":       "sent",
    }).execute()

    confirm_text = TICKET_MSG.format(
        name=guest["name"],
        event_name=event["name"],
        event_date=event["date"],
    )
    await greenapi.send_text(guest["phone"], confirm_text)
    await greenapi.send_image(
        guest["phone"],
        qr_url,
        caption=f"Entry ticket — {event['name']}",
    )


@router.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Green API POSTs here on every incoming message.
    Handles guest replies: 1 = confirm attendance, 2 = decline.
    Always returns 200 — errors are logged, never surfaced to Green API.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}

    # Green API webhook body structure
    body     = payload.get("body", {})
    msg_type = body.get("typeMessage")

    if msg_type != "textMessage":
        return {"status": "ignored", "reason": "not a text message"}

    sender_data = body.get("senderData", {})
    raw_phone   = sender_data.get("sender", "")    # e.g. "201039048775@c.us"
    phone       = raw_phone.replace("@c.us", "").replace("@g.us", "")

    text = (
        body.get("messageData", {})
            .get("textMessageData", {})
            .get("textMessage", "")
            .strip()
    )

    if text not in ("1", "2"):
        # Send a helpful hint for unrecognised messages
        try:
            await greenapi.send_text(phone, INVALID_MSG)
        except Exception:
            pass
        return {"status": "ok"}

    sb = get_supabase()

    # Find the most recent active guest record for this phone number
    guest_res = (
        sb.table("p_guests")
        .select("*, events(*)")
        .eq("phone", phone)
        .in_("status", ["invited", "confirmed"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not guest_res.data:
        # Unknown number — ignore silently
        return {"status": "ok"}

    guest = guest_res.data[0]
    event = guest.get("events") or {}

    background_tasks.add_task(
        _handle_confirmation,
        guest=guest,
        event=event,
        replied_yes=(text == "1"),
    )

    return {"status": "processing"}
