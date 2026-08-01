import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import resend_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email", tags=["email"])


class TestEmailRequest(BaseModel):
    to: str


@router.post("/test")
async def send_test_email(body: TestEmailRequest):
    """
    Send a one-off test email via Resend to confirm the integration works.
    """
    html = """
    <div style="font-family:-apple-system,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <h2 style="color:#B8962E;">🎟️ Move Tick — Test Email</h2>
      <p>This is a test send confirming the Resend integration is wired up
      correctly for <strong>movetick@mbeg.org</strong>.</p>
      <p style="color:#888;font-size:13px;">If you received this, sending works.</p>
    </div>
    """
    try:
        result = await resend_email.send_email(
            to=body.to,
            subject="Move Tick — Resend Integration Test",
            html=html,
        )
    except Exception as e:
        logger.exception("Test email failed")
        raise HTTPException(500, detail=str(e))

    return {"sent": True, "resend_response": result}
