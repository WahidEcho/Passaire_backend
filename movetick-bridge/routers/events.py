import re
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


@router.post("/")
async def create_event(body: CreateEventRequest):
    sb = get_supabase()
    result = sb.table("p_events").insert(body.model_dump()).execute()
    return result.data[0]


@router.get("/")
async def list_events():
    sb = get_supabase()
    return sb.table("p_events").select("*").order("date", desc=True).execute().data


@router.get("/{event_id}")
async def get_event(event_id: str):
    """Accept either a UUID or a slug in the path."""
    sb = get_supabase()
    if _UUID_RE.match(event_id):
        result = sb.table("p_events").select("*").eq("id", event_id).single().execute()
    else:
        result = sb.table("p_events").select("*").eq("slug", event_id).single().execute()
    if not result.data:
        raise HTTPException(404, "Event not found")
    return result.data
