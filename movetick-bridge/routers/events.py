import re
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.supabase_client import get_supabase

router = APIRouter(prefix="/events", tags=["events"])

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class CreateEventRequest(BaseModel):
    name: str
    date: str        # YYYY-MM-DD
    venue: str = ""
    gate_count: int = 1
    slug: Optional[str] = None
    manager_passcode: Optional[str] = None
    guard_passcode: Optional[str] = None


class UpdateEventRequest(BaseModel):
    name: Optional[str] = None
    date: Optional[str] = None
    venue: Optional[str] = None
    gate_count: Optional[int] = None


@router.post("/")
async def create_event(body: CreateEventRequest):
    sb = get_supabase()
    result = sb.table("p_events").insert(body.model_dump()).execute()
    return result.data[0]


@router.get("/")
async def list_events():
    sb = get_supabase()
    return sb.table("p_events").select("*").order("date", desc=True).execute().data


@router.get("/summary")
async def events_summary():
    """
    Aggregate stats across every event — guest counts by status and
    message counts by status — plus grand totals. Must be registered
    above GET /{event_id} or FastAPI would capture "summary" as an id.
    """
    sb = get_supabase()
    events = sb.table("p_events").select("*").order("date", desc=True).execute().data or []
    guests = sb.table("p_guests").select("event_id, status").execute().data or []
    logs   = sb.table("p_message_log").select("event_id, status").execute().data or []

    guest_counts: dict = defaultdict(lambda: defaultdict(int))
    for g in guests:
        guest_counts[g["event_id"]][g["status"]] += 1
    msg_counts: dict = defaultdict(lambda: defaultdict(int))
    for m in logs:
        msg_counts[m["event_id"]][m["status"]] += 1

    def build_row(ev):
        gc, mc = guest_counts.get(ev["id"], {}), msg_counts.get(ev["id"], {})
        return {
            "id": ev["id"], "name": ev["name"], "date": ev["date"], "venue": ev.get("venue"),
            "gate_count": ev.get("gate_count", 1),
            "guest_count": sum(gc.values()),
            "invited": gc.get("invited", 0), "confirmed": gc.get("confirmed", 0),
            "declined": gc.get("declined", 0), "checked_in": gc.get("checked_in", 0),
            "messages_sent": sum(mc.get(s, 0) for s in ("sent", "delivered", "read")),
            "messages_delivered": mc.get("delivered", 0) + mc.get("read", 0),
            "messages_failed": mc.get("failed", 0),
            "messages_bounced": mc.get("bounced", 0) + mc.get("complained", 0),
        }

    rows = [build_row(ev) for ev in events]
    grand = {k: sum(r[k] for r in rows) for k in
             ("guest_count", "checked_in", "confirmed", "invited", "declined",
              "messages_sent", "messages_delivered", "messages_failed", "messages_bounced")}
    grand["events"] = len(events)
    return {"grand_totals": grand, "events": rows}


@router.get("/{event_id}")
async def get_event(event_id: str):
    """Accept either a UUID or a slug in the path."""
    sb = get_supabase()
    if _UUID_RE.match(event_id):
        result = sb.table("p_events").select("*").eq("id", event_id).limit(1).execute()
    else:
        result = sb.table("p_events").select("*").eq("slug", event_id).limit(1).execute()
    if not result.data:
        raise HTTPException(404, "Event not found")
    return result.data[0]


@router.patch("/{event_id}")
async def update_event(event_id: str, body: UpdateEventRequest):
    sb = get_supabase()
    updates = body.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields provided to update")
    result = sb.table("p_events").update(updates).eq("id", event_id).execute()
    if not result.data:
        raise HTTPException(404, "Event not found")
    return result.data[0]


@router.get("/{event_id}/delivery-log")
async def event_delivery_log(event_id: str, limit: int = 100):
    sb = get_supabase()
    res = (
        sb.table("p_message_log")
        .select("id, guest_id, channel, message_type, recipient, status, error_detail, "
                "sent_at, delivered_at, read_at, failed_at, created_at, p_guests(name)")
        .eq("event_id", event_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = res.data or []
    for r in rows:
        guest = r.pop("p_guests", None) or {}
        r["guest_name"] = guest.get("name")
    return rows
