import io
import uuid
import qrcode
from PIL import Image, ImageDraw, ImageFont
from services.supabase_client import get_supabase

# ── Zone colours (for badge) ─────────────────────────────────────────────────
ZONE_COLOURS = {
    "blue":  {"bg": "#1D4ED8", "text": "#FFFFFF"},
    "red":   {"bg": "#B91C1C", "text": "#FFFFFF"},
    "green": {"bg": "#15803D", "text": "#FFFFFF"},
}
DEFAULT_ZONE = {"bg": "#4B5563", "text": "#F9FAFB"}

# ── Palette ───────────────────────────────────────────────────────────────────
BG           = "#FEFEF8"          # warm white
GOLD         = "#B8962E"          # deep gold
GOLD_LIGHT   = "#D4AF5A"          # corner accent
BLACK        = "#1A1A1A"
GREY         = "#6B7280"
BORDER_GREY  = "#E5E4DC"

CANVAS_W = 800
CANVAS_H = 1060


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
         "/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
    ]
    for bold_path, normal_path in paths:
        try:
            return ImageFont.truetype(bold_path if bold else normal_path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_corners(draw: ImageDraw.ImageDraw, margin: int = 28,
                  length: int = 52, thick: int = 3):
    """Draw elegant gold L-shaped corner brackets."""
    w, h = CANVAS_W, CANVAS_H
    m, ln = margin, length
    c = GOLD_LIGHT

    # Top-left
    draw.rectangle([m, m, m + ln, m + thick], fill=c)
    draw.rectangle([m, m, m + thick, m + ln], fill=c)
    # Top-right
    draw.rectangle([w - m - ln, m, w - m, m + thick], fill=c)
    draw.rectangle([w - m - thick, m, w - m, m + ln], fill=c)
    # Bottom-left
    draw.rectangle([m, h - m - thick, m + ln, h - m], fill=c)
    draw.rectangle([m, h - m - ln, m + thick, h - m], fill=c)
    # Bottom-right
    draw.rectangle([w - m - ln, h - m - thick, w - m, h - m], fill=c)
    draw.rectangle([w - m - thick, h - m - ln, w - m, h - m], fill=c)


def _centered_text(draw: ImageDraw.ImageDraw, y: int, text: str,
                   font, fill: str, canvas_w: int = CANVAS_W):
    draw.text((canvas_w // 2, y), text, font=font, fill=fill, anchor="mm")


def _rounded_badge(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                   text: str, font, bg: str, fg: str, pad_x=28, pad_h=18):
    bbox  = font.getbbox(text)
    tw    = bbox[2] - bbox[0]
    bw, bh = tw + pad_x * 2, pad_h * 2 + (bbox[3] - bbox[1])
    x0, y0 = cx - bw // 2, cy - bh // 2
    draw.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=bh // 2, fill=bg)
    draw.text((cx, cy), text, font=font, fill=fg, anchor="mm")


def _thin_line(draw: ImageDraw.ImageDraw, y: int, colour=GOLD_LIGHT,
               margin=80, h=1):
    draw.rectangle([margin, y, CANVAS_W - margin, y + h], fill=colour)


def _generate_qr_image(token: str, guest_name: str, event_name: str,
                        zone: str | None = None) -> bytes:

    zone_key = (zone or "").lower()
    zc       = ZONE_COLOURS.get(zone_key, DEFAULT_ZONE)
    z_label  = zone.upper() if zone else "GENERAL"

    # ── QR code ───────────────────────────────────────────────────────────────
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=9,
        border=2,
    )
    qr.add_data(token)
    qr.make(fit=True)
    qr_pil = (
        qr.make_image(fill_color=BLACK, back_color="white")
          .get_image()
          .convert("RGB")
    )

    # ── Canvas ────────────────────────────────────────────────────────────────
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), color=BG)
    draw   = ImageDraw.Draw(canvas)

    # Outer border (thin full rectangle)
    draw.rectangle([18, 18, CANVAS_W - 18, CANVAS_H - 18],
                   outline=BORDER_GREY, width=1)

    # Gold corner brackets
    _draw_corners(draw)

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_sub     = _get_font(22)
    f_title   = _get_font(54, bold=True)
    f_title2  = _get_font(48, bold=True)   # fallback for long names
    f_confirm = _get_font(28, bold=True)
    f_label   = _get_font(20)
    f_name    = _get_font(30, bold=True)
    f_zone    = _get_font(18, bold=True)
    f_qrlabel = _get_font(22, bold=True)
    f_footer  = _get_font(18)

    # ── Event subtitle (small, top) ───────────────────────────────────────────
    _centered_text(draw, 72, event_name, f_sub, GREY)

    # ── Gold divider thin ────────────────────────────────────────────────────
    _thin_line(draw, 90)

    # ── Large gold event title ────────────────────────────────────────────────
    # Wrap long names across 2 lines automatically
    words    = event_name.split()
    mid      = len(words) // 2
    line1    = " ".join(words[:mid]) if len(words) > 3 else event_name
    line2    = " ".join(words[mid:]) if len(words) > 3 else ""

    if line2:
        _centered_text(draw, 165, line1, f_title, GOLD)
        _centered_text(draw, 230, line2, f_title, GOLD)
        title_bottom = 265
    else:
        _centered_text(draw, 195, line1, f_title, GOLD)
        title_bottom = 230

    # ── Gold divider ──────────────────────────────────────────────────────────
    _thin_line(draw, title_bottom + 10)

    # ── "Digital Event Confirmation" ─────────────────────────────────────────
    confirm_y = title_bottom + 48
    _centered_text(draw, confirm_y, "Digital Event Confirmation", f_confirm, BLACK)

    # ── Thin divider ─────────────────────────────────────────────────────────
    _thin_line(draw, confirm_y + 28, colour="#D4AF5A55")

    # ── Invited name ──────────────────────────────────────────────────────────
    name_y = confirm_y + 66
    _centered_text(draw, name_y, "Invited Name:", f_label, GREY)
    _centered_text(draw, name_y + 38, guest_name, f_name, BLACK)

    # ── Zone badge ────────────────────────────────────────────────────────────
    badge_y = name_y + 82
    _rounded_badge(draw, CANVAS_W // 2, badge_y,
                   f"ZONE  {z_label}", f_zone, zc["bg"], zc["text"])

    # ── "QR CODE" label ───────────────────────────────────────────────────────
    qr_label_y = badge_y + 48
    _centered_text(draw, qr_label_y, "QR CODE", f_qrlabel, GREY)

    # ── QR image ──────────────────────────────────────────────────────────────
    qr_size = 380
    qr_pil  = qr_pil.resize((qr_size, qr_size), Image.LANCZOS)
    qr_x    = (CANVAS_W - qr_size) // 2
    qr_y    = qr_label_y + 22
    canvas.paste(qr_pil, (qr_x, qr_y))

    # ── Gold divider below QR ─────────────────────────────────────────────────
    div_y = qr_y + qr_size + 18
    _thin_line(draw, div_y)

    # ── "Scan at Entrance" ────────────────────────────────────────────────────
    _centered_text(draw, div_y + 34, "Scan at Entrance", f_confirm, BLACK)

    # ── Ticket ID + branding ──────────────────────────────────────────────────
    _centered_text(draw, CANVAS_H - 44,
                   f"ID: {token[:8].upper()}  ·  Powered by Passaire",
                   f_footer, GREY)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", quality=95)
    return buf.getvalue()


def create_ticket_qr(guest_id: str, event_id: str,
                     guest_name: str, event_name: str,
                     zone: str | None = None) -> tuple[str, str]:
    """
    Generate a premium QR ticket, upload to Supabase Storage bucket 'tickets'.
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
