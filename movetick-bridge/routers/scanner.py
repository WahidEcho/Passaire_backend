import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.supabase_client import get_supabase

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
    - Second scan → checked_out  (toggle)
    Returns guest info on valid scan, 404 on invalid token.
    """
    sb = get_supabase()

    ticket_res = (
        sb.table("tickets")
        .select("*, guests(*), events(*)")
        .eq("token", body.token)
        .single()
        .execute()
    )

    if not ticket_res.data:
        raise HTTPException(404, detail={
            "valid": False,
            "reason": "Ticket not found",
        })

    ticket = ticket_res.data
    guest  = ticket.get("guests") or {}
    event  = ticket.get("events") or {}

    if guest.get("status") == "checked_in":
        # Already inside — log as check-out
        sb.table("guests").update({"status": "confirmed"}).eq("id", guest["id"]).execute()
        sb.table("scan_logs").insert({
            "ticket_id":   ticket["id"],
            "gate_number": body.gate_number,
            "action":      "checked_out",
        }).execute()
        return {
            "valid":   True,
            "action":  "checked_out",
            "guest":   {
                "name":      guest["name"],
                "phone":     guest["phone"],
                "ticket_id": ticket["id"][:8].upper(),
            },
            "event":   event.get("name"),
            "message": f"Checked OUT: {guest['name']}",
        }

    # Check in
    sb.table("guests").update({"status": "checked_in"}).eq("id", guest["id"]).execute()
    sb.table("scan_logs").insert({
        "ticket_id":   ticket["id"],
        "gate_number": body.gate_number,
        "action":      "checked_in",
    }).execute()

    return {
        "valid":   True,
        "action":  "checked_in",
        "guest":   {
            "name":      guest["name"],
            "phone":     guest["phone"],
            "ticket_id": ticket["id"][:8].upper(),
        },
        "event":   event.get("name"),
        "message": f"Welcome, {guest['name']}!",
    }


@router.get("/logs/{event_id}")
async def scan_logs(event_id: str, limit: int = 50):
    """Return recent scan logs for an event."""
    sb = get_supabase()

    # Fetch ticket IDs for this event first (Supabase SDK can't filter
    # scan_logs by a foreign-table column in a single query)
    tickets_res = (
        sb.table("tickets")
        .select("id")
        .eq("event_id", event_id)
        .execute()
    )
    ticket_ids = [t["id"] for t in (tickets_res.data or [])]
    if not ticket_ids:
        return []

    logs = (
        sb.table("scan_logs")
        .select("*, tickets(token, guests(name, phone))")
        .in_("ticket_id", ticket_ids)
        .order("scanned_at", desc=True)
        .limit(limit)
        .execute()
    )
    return logs.data


@router.get("/live/{event_id}")
async def live_stats(event_id: str):
    """Live dashboard stats for the event."""
    sb = get_supabase()
    guests = sb.table("guests").select("status").eq("event_id", event_id).execute()
    counts: dict = {}
    for g in guests.data:
        s = g["status"]
        counts[s] = counts.get(s, 0) + 1
    return {
        "total_confirmed":   counts.get("confirmed", 0) + counts.get("checked_in", 0),
        "currently_inside":  counts.get("checked_in", 0),
        "total_invited":     counts.get("invited", 0),
        "declined":          counts.get("declined", 0),
        "breakdown":         counts,
    }
