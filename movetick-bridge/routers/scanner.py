import logging
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scanner", tags=["scanner"])


class ScanRequest(BaseModel):
    token: str
    gate_number: int = 1


# ── helpers ───────────────────────────────────────────────────────────────────

def _ticket_ids_for_event(sb, event_id: str) -> list[str]:
    res = sb.table("p_tickets").select("id").eq("event_id", event_id).execute()
    return [t["id"] for t in (res.data or [])]


def _reshape_log(log: dict) -> dict:
    ticket = log.get("p_tickets") or {}
    guest  = ticket.get("p_guests") or {}
    return {
        "id":         log["id"],
        "guest_name": guest.get("name"),
        "guest_id":   log.get("guest_id") or guest.get("id"),
        "action":     log["action"],
        "scanned_at": log["scanned_at"],
        "gate_number": log.get("gate_number"),
    }


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/scan")
async def scan_ticket(body: ScanRequest):
    """
    Gate scanner endpoint.
    - First scan  → checked_in
    - Second scan → checked_out (toggle)
    Returns guest info on valid scan, 404 on invalid token.
    """
    sb = get_supabase()

    ticket_res = (
        sb.table("p_tickets")
        .select("*, p_guests(*), p_events(*)")
        .eq("token", body.token)
        .single()
        .execute()
    )

    if not ticket_res.data:
        raise HTTPException(404, detail={"valid": False, "reason": "Ticket not found"})

    ticket = ticket_res.data
    guest  = ticket.get("p_guests") or {}
    event  = ticket.get("p_events") or {}

    if guest.get("status") == "checked_in":
        sb.table("p_guests").update({"status": "confirmed"}).eq("id", guest["id"]).execute()
        sb.table("p_scan_logs").insert({
            "ticket_id":   ticket["id"],
            "guest_id":    guest["id"],
            "gate_number": body.gate_number,
            "action":      "checked_out",
        }).execute()
        return {
            "valid":   True,
            "action":  "checked_out",
            "guest": {
                "name":      guest["name"],
                "phone":     guest["phone"],
                "zone":      guest.get("zone"),
                "ticket_id": ticket["id"][:8].upper(),
            },
            "event":   event.get("name"),
            "message": f"Checked OUT: {guest['name']}",
        }

    sb.table("p_guests").update({"status": "checked_in"}).eq("id", guest["id"]).execute()
    sb.table("p_scan_logs").insert({
        "ticket_id":   ticket["id"],
        "guest_id":    guest["id"],
        "gate_number": body.gate_number,
        "action":      "checked_in",
    }).execute()

    return {
        "valid":   True,
        "action":  "checked_in",
        "guest": {
            "name":      guest["name"],
            "phone":     guest["phone"],
            "zone":      guest.get("zone"),
            "ticket_id": ticket["id"][:8].upper(),
        },
        "event":   event.get("name"),
        "message": f"Welcome, {guest['name']}!",
    }


@router.get("/preview/{token}")
async def preview_ticket(token: str):
    """
    Look up a ticket by token WITHOUT performing check-in or check-out.
    Safe to call for preview/display purposes.
    """
    sb = get_supabase()

    ticket_res = (
        sb.table("p_tickets")
        .select("*, p_guests(*)")
        .eq("token", token)
        .single()
        .execute()
    )

    if not ticket_res.data:
        raise HTTPException(404, detail={"reason": "Ticket not found"})

    guest = ticket_res.data.get("p_guests") or {}
    return {
        "guest": {
            "id":     guest.get("id"),
            "name":   guest.get("name"),
            "phone":  guest.get("phone"),
            "zone":   guest.get("zone"),
            "status": guest.get("status"),
        }
    }


@router.get("/live/{event_id}")
async def live_stats(event_id: str):
    """Live dashboard stats for an event."""
    sb = get_supabase()

    guests = sb.table("p_guests").select("status").eq("event_id", event_id).execute()
    counts: dict = {}
    for g in guests.data:
        s = g["status"]
        counts[s] = counts.get(s, 0) + 1

    # Total check-in entries ever recorded for this event
    ticket_ids = _ticket_ids_for_event(sb, event_id)
    total_entries = 0
    if ticket_ids:
        logs_res = (
            sb.table("p_scan_logs")
            .select("id", count="exact")
            .in_("ticket_id", ticket_ids)
            .eq("action", "checked_in")
            .execute()
        )
        total_entries = logs_res.count or 0

    return {
        "total_confirmed":  counts.get("confirmed", 0) + counts.get("checked_in", 0),
        "currently_inside": counts.get("checked_in", 0),
        "total_invited":    counts.get("invited", 0),
        "declined":         counts.get("declined", 0),
        "total_entries":    total_entries,
        "breakdown":        counts,
    }


@router.get("/hourly/{event_id}")
async def hourly_stats(event_id: str):
    """
    Scan counts grouped by hour of day (0–23) for today (UTC).
    Only hours with at least 1 scan are included.
    """
    sb = get_supabase()

    ticket_ids = _ticket_ids_for_event(sb, event_id)
    if not ticket_ids:
        return []

    now_utc    = datetime.now(timezone.utc)
    day_start  = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    day_end    = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

    logs_res = (
        sb.table("p_scan_logs")
        .select("scanned_at")
        .in_("ticket_id", ticket_ids)
        .gte("scanned_at", day_start)
        .lte("scanned_at", day_end)
        .execute()
    )

    hour_counts: dict[int, int] = defaultdict(int)
    for log in (logs_res.data or []):
        scanned_at = log.get("scanned_at", "")
        try:
            dt = datetime.fromisoformat(scanned_at.replace("Z", "+00:00"))
            hour_counts[dt.hour] += 1
        except (ValueError, AttributeError):
            pass

    return [{"hour": h, "count": c} for h, c in sorted(hour_counts.items())]


@router.get("/logs/{event_id}")
async def scan_logs(event_id: str, limit: int = 50):
    """Return recent scan logs for an event, including guest_id."""
    sb = get_supabase()

    ticket_ids = _ticket_ids_for_event(sb, event_id)
    if not ticket_ids:
        return []

    logs_res = (
        sb.table("p_scan_logs")
        .select("*, p_tickets(token, p_guests(id, name, phone, zone))")
        .in_("ticket_id", ticket_ids)
        .order("scanned_at", desc=True)
        .limit(limit)
        .execute()
    )

    return [_reshape_log(log) for log in (logs_res.data or [])]
