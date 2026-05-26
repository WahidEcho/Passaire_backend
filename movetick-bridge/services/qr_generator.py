import io
import uuid
import qrcode
from PIL import Image, ImageDraw, ImageFont
from services.supabase_client import get_supabase


def _generate_qr_image(token: str, guest_name: str, event_name: str) -> bytes:
    """Generate a styled QR code image and return raw PNG bytes."""

    # Generate QR and extract the underlying PIL image
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(token)
    qr.make(fit=True)

    # get_image() returns the raw PIL Image from the qrcode wrapper
    qr_pil = qr.make_image(fill_color="#1a1a2e", back_color="white").get_image().convert("RGB")

    # Canvas
    canvas_w, canvas_h = 600, 750
    canvas = Image.new("RGB", (canvas_w, canvas_h), color="#1a1a2e")

    # Paste QR centred on canvas
    qr_size = 400
    qr_pil = qr_pil.resize((qr_size, qr_size))
    qr_x = (canvas_w - qr_size) // 2
    canvas.paste(qr_pil, (qr_x, 180))

    draw = ImageDraw.Draw(canvas)

    # Try to load a font; fall back to default if not available on the server
    try:
        font_title  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_normal = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_small  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        font_title  = ImageFont.load_default()
        font_normal = font_title
        font_small  = font_title

    # Event name (top)
    draw.text((canvas_w // 2, 40), event_name, font=font_title,
              fill="#FFFFFF", anchor="mm")

    # Divider line
    draw.line([(60, 90), (540, 90)], fill="#5B3BE8", width=2)

    # Guest name
    draw.text((canvas_w // 2, 130), guest_name, font=font_normal,
              fill="#D0CFFF", anchor="mm")

    # Short token ID below QR
    draw.text((canvas_w // 2, 615), f"ID: {token[:8].upper()}", font=font_small,
              fill="#888888", anchor="mm")

    # Footer
    draw.text((canvas_w // 2, 710), "Powered by Passaire · Move Beyond",
              font=font_small, fill="#444466", anchor="mm")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def create_ticket_qr(guest_id: str, event_id: str,
                     guest_name: str, event_name: str) -> tuple[str, str]:
    """
    Generate a styled QR ticket, upload to Supabase Storage bucket 'tickets'.
    Returns (token, public_image_url).

    The token is a random UUID — stored in the tickets table and encoded
    inside the QR. Each guest gets a unique token at confirmation time.
    """
    token     = str(uuid.uuid4())
    png_bytes = _generate_qr_image(token, guest_name, event_name)
    file_path = f"{event_id}/{guest_id}.png"

    sb = get_supabase()

    # upsert=true so re-confirmations don't raise a duplicate-file error
    sb.storage.from_("tickets").upload(
        path=file_path,
        file=png_bytes,
        file_options={"content-type": "image/png", "upsert": "true"},
    )

    public_url = sb.storage.from_("tickets").get_public_url(file_path)
    return token, public_url
