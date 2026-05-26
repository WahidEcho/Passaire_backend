import io
import uuid
import qrcode
from PIL import Image, ImageDraw, ImageFont
from services.supabase_client import get_supabase

# ── Zone colour palette ───────────────────────────────────────────────────────
ZONE_COLOURS = {
    "blue":  {"bg": "#1D4ED8", "badge_text": "#FFFFFF", "glow": "#3B82F6"},
    "red":   {"bg": "#B91C1C", "badge_text": "#FFFFFF", "glow": "#EF4444"},
    "green": {"bg": "#15803D", "badge_text": "#FFFFFF", "glow": "#22C55E"},
}
DEFAULT_ZONE = {"bg": "#374151", "badge_text": "#D1D5DB", "glow": "#6B7280"}

CANVAS_W  = 640
CANVAS_H  = 900
BG_COLOUR = "#08080F"           # near-black background
ACCENT    = "#7C3AED"           # purple accent line


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths_bold   = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    paths_normal = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in (paths_bold if bold else paths_normal):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill: str):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


def _generate_qr_image(token: str, guest_name: str, event_name: str,
                        zone: str | None = None) -> bytes:

    zone_key    = (zone or "").lower()
    zone_colour = ZONE_COLOURS.get(zone_key, DEFAULT_ZONE)
    zone_label  = zone.upper() if zone else "GENERAL"

    # ── Build QR ──────────────────────────────────────────────────────────────
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=9,
        border=2,
    )
    qr.add_data(token)
    qr.make(fit=True)
    qr_pil = qr.make_image(fill_color="#08080F", back_color="white").get_image().convert("RGB")

    # ── Canvas ────────────────────────────────────────────────────────────────
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), color=BG_COLOUR)
    draw   = ImageDraw.Draw(canvas)

    # Top accent bar (full width, zone colour)
    draw.rectangle([0, 0, CANVAS_W, 8], fill=zone_colour["glow"])

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_event  = _get_font(44, bold=True)
    f_name   = _get_font(32, bold=True)
    f_zone   = _get_font(20, bold=True)
    f_small  = _get_font(16)
    f_id     = _get_font(14)

    # ── Event name ────────────────────────────────────────────────────────────
    draw.text((CANVAS_W // 2, 58), event_name,
              font=f_event, fill="#FFFFFF", anchor="mm")

    # Thin divider line
    draw.rectangle([60, 88, CANVAS_W - 60, 90], fill=ACCENT)

    # ── Guest name ────────────────────────────────────────────────────────────
    draw.text((CANVAS_W // 2, 120), guest_name,
              font=f_name, fill="#E2E8F0", anchor="mm")

    # ── Zone badge ────────────────────────────────────────────────────────────
    badge_w, badge_h = 160, 38
    badge_x = (CANVAS_W - badge_w) // 2
    badge_y = 148
    _rounded_rect(draw, [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                  radius=19, fill=zone_colour["bg"])
    draw.text((CANVAS_W // 2, badge_y + badge_h // 2),
              f"ZONE  {zone_label}",
              font=f_zone, fill=zone_colour["badge_text"], anchor="mm")

    # ── QR code ───────────────────────────────────────────────────────────────
    qr_size = 420
    qr_pil  = qr_pil.resize((qr_size, qr_size), Image.LANCZOS)

    # White card behind QR
    qr_x = (CANVAS_W - qr_size) // 2
    qr_y = 208
    _rounded_rect(draw, [qr_x - 16, qr_y - 16, qr_x + qr_size + 16, qr_y + qr_size + 16],
                  radius=16, fill="#FFFFFF")
    canvas.paste(qr_pil, (qr_x, qr_y))

    # ── Divider ───────────────────────────────────────────────────────────────
    div_y = qr_y + qr_size + 32
    draw.rectangle([60, div_y, CANVAS_W - 60, div_y + 1], fill="#1E2433")

    # ── Ticket ID ─────────────────────────────────────────────────────────────
    draw.text((CANVAS_W // 2, div_y + 26),
              f"TICKET  {token[:8].upper()}",
              font=f_id, fill="#475569", anchor="mm")

    # ── Bottom accent bar + branding ──────────────────────────────────────────
    draw.rectangle([0, CANVAS_H - 6, CANVAS_W, CANVAS_H], fill=zone_colour["glow"])
    draw.text((CANVAS_W // 2, CANVAS_H - 32),
              "Powered by Passaire  ·  Move Beyond",
              font=f_small, fill="#334155", anchor="mm")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", quality=95)
    return buf.getvalue()


def create_ticket_qr(guest_id: str, event_id: str,
                     guest_name: str, event_name: str,
                     zone: str | None = None) -> tuple[str, str]:
    """
    Generate a premium styled QR ticket, upload to Supabase Storage bucket 'tickets'.
    Returns (token, public_image_url).
    """
    token     = str(uuid.uuid4())
    png_bytes = _generate_qr_image(token, guest_name, event_name, zone)
    file_path = f"{event_id}/{guest_id}.png"

    sb = get_supabase()
    sb.storage.from_("tickets").upload(
        path=file_path,
        file=png_bytes,
        file_options={"content-type": "image/png", "upsert": "true"},
    )

    public_url = sb.storage.from_("tickets").get_public_url(file_path)
    return token, public_url
