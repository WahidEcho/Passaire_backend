"""
/mp-state  — tiny key-value store backed by Supabase Storage.
Lets the invitation HTML page persist progress online (no extra DB table).
"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from services.supabase_client import get_supabase

router = APIRouter(prefix="/mp-state", tags=["state"])

BUCKET     = "tickets"
STATE_PATH = "mp-state/current.json"
EMPTY      = {"done": [], "noWa": [], "extras": []}


@router.get("", summary="Read current invitation progress")
async def get_state():
    """Return current progress JSON (or empty state if not yet saved)."""
    sb = get_supabase()
    try:
        raw = sb.storage.from_(BUCKET).download(STATE_PATH)
        return JSONResponse(content=json.loads(raw))
    except Exception:
        return JSONResponse(content=EMPTY)


@router.post("", summary="Save invitation progress")
async def save_state(body: dict):
    """Overwrite progress JSON in Supabase Storage."""
    sb = get_supabase()
    content = json.dumps(body).encode()
    try:
        # Try upload with upsert=true first
        sb.storage.from_(BUCKET).upload(
            path=STATE_PATH,
            file=content,
            file_options={"content-type": "application/json", "upsert": "true"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}
