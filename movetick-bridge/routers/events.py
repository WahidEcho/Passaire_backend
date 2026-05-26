from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.supabase_client import get_supabase

router = APIRouter(prefix="/events", tags=["events"])


class CreateEventRequest(BaseModel):
    name: str
    date: str        # YYYY-MM-DD
    venue: str = ""
    gate_count: int = 1


@router.post("/")
async def create_event(body: CreateEventRequest):
    sb = get_supabase()
    result = sb.table("events").insert(body.model_dump()).execute()
    return result.data[0]


@router.get("/")
async def list_events():
    sb = get_supabase()
    return sb.table("events").select("*").order("date", desc=True).execute().data


@router.get("/{event_id}")
async def get_event(event_id: str):
    sb = get_supabase()
    result = sb.table("events").select("*").eq("id", event_id).single().execute()
    if not result.data:
        raise HTTPException(404, "Event not found")
    return result.data
