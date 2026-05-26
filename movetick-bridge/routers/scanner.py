import logging
import traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.supabase_client import get_supabase
from services.qr_generator import create_ticket_qr

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scanner", tags=["scanner"])


class ScanRequest(BaseModel):
    token: str
    gate_number: int = 1


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


@router.get("/logs/{event_id}")
async def scan_logs(event_id: str, limit: int = 50):
    """Return recent scan logs for an event."""
    sb = get_supabase()

    tickets_res = (
        sb.table("p_tickets")
        .select("id")
        .eq("event_id", event_id)
        .execute()
    )
    ticket_ids = [t["id"] for t in (tickets_res.data or [])]
    if not ticket_ids:
        return []

    logs = (
        sb.table("p_scan_logs")
        .select("*, p_tickets(token, p_guests(name, phone, zone))")
        .in_("ticket_id", ticket_ids)
        .order("scanned_at", desc=True)
        .limit(limit)
        .execute()
    )
    return logs.data


@router.get("/live/{event_id}")
async def live_stats(event_id: str):
    """Live dashboard stats for an event."""
    sb = get_supabase()
    guests = sb.table("p_guests").select("status").eq("event_id", event_id).execute()
    counts: dict = {}
    for g in guests.data:
        s = g["status"]
        counts[s] = counts.get(s, 0) + 1
    return {
        "total_confirmed":  counts.get("confirmed", 0) + counts.get("checked_in", 0),
        "currently_inside": counts.get("checked_in", 0),
        "total_invited":    counts.get("invited", 0),
        "declined":         counts.get("declined", 0),
        "breakdown":        counts,
    }


@router.get("/debug/qr-test/{event_id}/{guest_id}")
async def debug_qr_test(event_id: str, guest_id: str):
    """Temporary debug: run QR generation synchronously and return error detail."""
    sb = get_supabase()
    guest_res = sb.table("p_guests").select("*").eq("id", guest_id).single().execute()
    if not guest_res.data:
        return {"error": "guest not found"}
    guest = guest_res.data
    try:
        token, qr_url = create_ticket_qr(
            guest_id=guest["id"],
            event_id=event_id,
            guest_name=guest["name"],
            event_name="Move Beyond Night",
            zone=guest.get("zone"),
        )
        return {"ok": True, "token": token[:8], "qr_url": qr_url}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}
