import io
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from services.supabase_client import get_supabase

router = APIRouter(prefix="/guests", tags=["guests"])


def _normalise_phone(raw: str) -> str:
    """
    Strip spaces, dashes, and leading +.
    Handle Egyptian numbers starting with 0 (prepend country code 20).
    Result is international format WITHOUT +, e.g. 201039048775
    """
    phone = str(raw).strip().replace(" ", "").replace("-", "").replace("+", "")
    if phone.startswith("0"):
        phone = "20" + phone[1:]
    return phone


@router.post("/upload")
async def upload_guests(
    event_id: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Upload a CSV or Excel file with columns: name, phone
    Upserts guests into the database (skips duplicates by event_id + phone).
    """
    content = await file.read()

    try:
        if (file.filename or "").endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(content), dtype=str)
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")

    # Flexible column matching
    df.columns = [c.strip().lower() for c in df.columns]
    name_col  = next((c for c in df.columns if "name" in c), None)
    phone_col = next((c for c in df.columns if "phone" in c or "mobile" in c or "number" in c), None)

    if not name_col or not phone_col:
        raise HTTPException(400, "File must have columns: name, phone")

    df = df[[name_col, phone_col]].dropna()
    df.columns = ["name", "phone"]
    df["phone"]    = df["phone"].apply(_normalise_phone)
    df["event_id"] = event_id
    df["status"]   = "invited"

    records = df.to_dict(orient="records")
    if not records:
        return {"inserted": 0, "message": "File contained no valid rows"}

    sb = get_supabase()
    # Upsert — skip duplicates silently on (event_id, phone)
    sb.table("p_guests").upsert(records, on_conflict="event_id,phone").execute()

    return {"inserted": len(records)}


@router.get("/{event_id}")
async def list_guests(event_id: str, status: str | None = None):
    sb = get_supabase()
    query = sb.table("p_guests").select("*").eq("event_id", event_id)
    if status:
        query = query.eq("status", status)
    result = query.order("name").execute()
    return result.data


@router.get("/{event_id}/stats")
async def guest_stats(event_id: str):
    sb = get_supabase()
    all_guests = sb.table("p_guests").select("status").eq("event_id", event_id).execute()
    counts: dict = {}
    for g in all_guests.data:
        s = g["status"]
        counts[s] = counts.get(s, 0) + 1
    total = len(all_guests.data)
    return {"total": total, "breakdown": counts}
