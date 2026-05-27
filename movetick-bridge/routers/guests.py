import io
import os
import asyncio
import logging
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import httpx
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from PIL import Image
from pyzbar.pyzbar import decode as qr_decode

from services.supabase_client import get_supabase
from services.qr_generator import create_ticket_qr
from services import greenapi

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/guests", tags=["guests"])

TICKET_MSG = """✅ *Your ticket is confirmed!*

Welcome, *{name}*!

Your QR code ticket for *{event_name}* is attached.
Please show this at the entrance.

📅 {event_date}
📍 {venue}

See you there! 🎉"""


def _normalise_phone(raw: str) -> str:
    phone = str(raw).strip().replace(" ", "").replace("-", "").replace("+", "")
    if phone.startswith("0"):
        phone = "20" + phone[1:]
    return phone


def _attach_qr_url(guest: dict) -> dict:
    """Flatten the nested p_tickets list to a top-level qr_url field."""
    tickets = guest.pop("p_tickets", None) or []
    if isinstance(tickets, list) and tickets:
        guest["qr_url"] = tickets[0].get("qr_image_url")
    elif isinstance(tickets, dict):
        guest["qr_url"] = tickets.get("qr_image_url")
    else:
        guest["qr_url"] = None
    return guest


async def _generate_and_send(guest: dict, event: dict):
    """Generate QR ticket and send directly via WhatsApp (no RSVP)."""
    sb = get_supabase()
    try:
        token, qr_url = create_ticket_qr(
            guest_id=guest["id"],
            event_id=event["id"],
            guest_name=guest["name"],
            event_name=event["name"],
            zone=guest.get("zone"),
        )
    except Exception as e:
        logger.error("[DIRECT] QR generation failed for %s: %s", guest["phone"], e)
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    sb.table("p_tickets").insert({
        "guest_id":     guest["id"],
        "event_id":     event["id"],
        "token":        token,
        "qr_image_url": qr_url,
        "sent_at":      now_iso,
    }).execute()

    sb.table("p_guests").update({"status": "confirmed"}).eq("id", guest["id"]).execute()

    caption = TICKET_MSG.format(
        name=guest["name"],
        event_name=event["name"],
        event_date=event.get("date", ""),
        venue=event.get("venue", "TBA"),
    )

    try:
        await greenapi.send_image(guest["phone"], qr_url, caption=caption)
        sb.table("p_wa_messages").insert({
            "phone":        guest["phone"],
            "message_type": "ticket",
            "status":       "sent",
        }).execute()
        logger.info("[DIRECT] Ticket sent to %s", guest["phone"])
    except Exception as e:
        logger.error("[DIRECT] WhatsApp send failed for %s: %s", guest["phone"], e)


# ── Upload ─────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_guests(
    background_tasks: BackgroundTasks,
    event_id:   str       = Form(...),
    send_mode:  str       = Form("rsvp"),   # "rsvp" | "direct"
    file:       UploadFile = File(...),
):
    """
    Upload CSV / Excel with columns: name, phone, zone (optional).

    send_mode=rsvp   → guests inserted with status 'invited', invitation sent
    send_mode=direct → QR tickets generated and sent immediately, no RSVP
    """
    content = await file.read()

    try:
        if (file.filename or "").endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(content), dtype=str)
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")

    df.columns = [c.strip().lower() for c in df.columns]
    name_col  = next((c for c in df.columns if "name"   in c), None)
    phone_col = next((c for c in df.columns if "phone"  in c or "mobile" in c or "number" in c), None)
    zone_col  = next((c for c in df.columns if "zone"   in c), None)

    if not name_col or not phone_col:
        raise HTTPException(400, "File must have columns: name, phone (zone optional)")

    cols = [name_col, phone_col] + ([zone_col] if zone_col else [])
    df   = df[cols].dropna(subset=[name_col, phone_col])
    df   = df.rename(columns={name_col: "name", phone_col: "phone",
                               **({zone_col: "zone"} if zone_col else {})})

    df["phone"]    = df["phone"].apply(_normalise_phone)
    df["event_id"] = event_id
    df["status"]   = "invited"
    if "zone" not in df.columns:
        df["zone"] = None

    records = df.to_dict(orient="records")
    if not records:
        return {"inserted": 0, "message": "File contained no valid rows"}

    sb = get_supabase()
    sb.table("p_guests").upsert(records, on_conflict="event_id,phone").execute()

    if send_mode == "direct":
        event_res = sb.table("p_events").select("*").eq("id", event_id).single().execute()
        if not event_res.data:
            raise HTTPException(404, "Event not found")
        event = event_res.data

        phones = [r["phone"] for r in records]
        guests_res = (
            sb.table("p_guests")
            .select("*")
            .eq("event_id", event_id)
            .in_("phone", phones)
            .execute()
        )
        guests = guests_res.data or []

        async def direct_bulk():
            for i, guest in enumerate(guests):
                await _generate_and_send(guest, event)
                if i < len(guests) - 1:
                    await asyncio.sleep(1.2)

        background_tasks.add_task(direct_bulk)
        return {"inserted": len(records), "mode": "direct", "sending": len(guests)}

    return {"inserted": len(records), "mode": "rsvp"}


# ── Detail by guest ID (must be defined before /{event_id} catch-all) ─────────

@router.get("/detail/{guest_id}")
async def get_guest_detail(guest_id: str):
    """Return a single guest by their own ID (not event ID)."""
    sb = get_supabase()
    res = (
        sb.table("p_guests")
        .select("*, p_tickets(qr_image_url)")
        .eq("id", guest_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Guest not found")
    guest = res.data
    tickets = guest.pop("p_tickets", None) or []
    if isinstance(tickets, list) and tickets:
        guest["qr_url"] = tickets[0].get("qr_image_url")
    elif isinstance(tickets, dict):
        guest["qr_url"] = tickets.get("qr_image_url")
    else:
        guest["qr_url"] = None
    return guest


# ── List guests for an event ───────────────────────────────────────────────────

@router.get("/{event_id}")
async def list_guests(event_id: str, status: str | None = None):
    """List all guests for an event, including zone and qr_url."""
    sb = get_supabase()
    query = (
        sb.table("p_guests")
        .select("*, p_tickets(qr_image_url)")
        .eq("event_id", event_id)
    )
    if status:
        query = query.eq("status", status)
    data = query.order("name").execute().data or []
    return [_attach_qr_url(g) for g in data]


@router.get("/{event_id}/stats")
async def guest_stats(event_id: str):
    sb     = get_supabase()
    data   = sb.table("p_guests").select("status").eq("event_id", event_id).execute().data
    counts: dict = {}
    for g in data:
        s = g["status"]
        counts[s] = counts.get(s, 0) + 1
    return {"total": len(data), "breakdown": counts}


# ── Guest scan history ─────────────────────────────────────────────────────────

@router.get("/{guest_id}/history")
async def guest_history(guest_id: str):
    """Return all scan events for a specific guest, ordered ascending."""
    sb = get_supabase()

    # Gather the guest's ticket IDs
    tickets_res = (
        sb.table("p_tickets")
        .select("id")
        .eq("guest_id", guest_id)
        .execute()
    )
    ticket_ids = [t["id"] for t in (tickets_res.data or [])]

    if not ticket_ids:
        return []

    logs_res = (
        sb.table("p_scan_logs")
        .select("action, scanned_at")
        .in_("ticket_id", ticket_ids)
        .order("scanned_at", desc=False)
        .execute()
    )

    return [
        {"action": log["action"], "timestamp": log["scanned_at"]}
        for log in (logs_res.data or [])
    ]


# ── Recover tickets from Storage ───────────────────────────────────────────────

@router.post("/{event_id}/recover-tickets")
async def recover_tickets_from_storage(event_id: str):
    """
    Reads every guest's existing QR PNG from Supabase Storage,
    decodes the embedded token, and inserts/upserts the row into p_tickets.
    Does NOT generate new images and does NOT send any WhatsApp messages.
    Safe to call multiple times (upsert on event_id+guest_id).
    """
    sb = get_supabase()
    event_res = sb.table("p_events").select("id").eq("id", event_id).maybe_single().execute()
    if not event_res.data:
        raise HTTPException(404, "Event not found")
    guests_res = sb.table("p_guests").select("id, name").eq("event_id", event_id).execute()
    guests = guests_res.data or []
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    storage_base = f"{supabase_url}/storage/v1/object/public/tickets"
    recovered = []
    failed = []
    for guest in guests:
        guest_id = guest["id"]
        file_path = f"{event_id}/{guest_id}.png"
        image_url = f"{storage_base}/{file_path}"
        try:
            resp = httpx.get(image_url, timeout=10)
            if resp.status_code != 200:
                failed.append({"guest_id": guest_id, "reason": f"Storage {resp.status_code}"})
                continue
            img = Image.open(BytesIO(resp.content))
            decoded = qr_decode(img)
            if not decoded:
                failed.append({"guest_id": guest_id, "reason": "QR decode failed"})
                continue
            token = decoded[0].data.decode("utf-8").strip()
            sb.table("p_tickets").upsert(
                {
                    "guest_id": guest_id,
                    "event_id": event_id,
                    "token": token,
                    "qr_image_url": image_url,
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="event_id,guest_id",
            ).execute()
            recovered.append(guest_id)
        except Exception as e:
            failed.append({"guest_id": guest_id, "reason": str(e)})
    return {
        "recovered": len(recovered),
        "failed": len(failed),
        "failures": failed,
    }


# ── Manual check-in / check-out ────────────────────────────────────────────────

@router.post("/{guest_id}/manual-checkin")
async def manual_checkin(guest_id: str):
    """Manually set a guest's status to checked_in and record a scan log."""
    sb = get_supabase()

    guest_res = sb.table("p_guests").select("id").eq("id", guest_id).single().execute()
    if not guest_res.data:
        raise HTTPException(404, "Guest not found")

    sb.table("p_guests").update({"status": "checked_in"}).eq("id", guest_id).execute()

    # Get ticket id if available (nullable in scan_logs schema)
    ticket_res = (
        sb.table("p_tickets")
        .select("id")
        .eq("guest_id", guest_id)
        .limit(1)
        .execute()
    )
    ticket_id = ticket_res.data[0]["id"] if ticket_res.data else None

    sb.table("p_scan_logs").insert({
        "ticket_id":   ticket_id,
        "guest_id":    guest_id,
        "gate_number": 0,
        "action":      "checked_in",
    }).execute()

    return {"success": True}


@router.post("/{guest_id}/manual-checkout")
async def manual_checkout(guest_id: str):
    """Manually revert a guest's status to confirmed and record a scan log."""
    sb = get_supabase()

    guest_res = sb.table("p_guests").select("id").eq("id", guest_id).single().execute()
    if not guest_res.data:
        raise HTTPException(404, "Guest not found")

    sb.table("p_guests").update({"status": "confirmed"}).eq("id", guest_id).execute()

    ticket_res = (
        sb.table("p_tickets")
        .select("id")
        .eq("guest_id", guest_id)
        .limit(1)
        .execute()
    )
    ticket_id = ticket_res.data[0]["id"] if ticket_res.data else None

    sb.table("p_scan_logs").insert({
        "ticket_id":   ticket_id,
        "guest_id":    guest_id,
        "gate_number": 0,
        "action":      "checked_out",
    }).execute()

    return {"success": True}
