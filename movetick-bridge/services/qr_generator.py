import io
import uuid
import qrcode
from PIL import Image, ImageDraw, ImageFont
from services.supabase_client import get_supabase

# ── Zone colours ──────────────────────────────────────────────────────────────
ZONE_COLOURS = {
    "blue":  {"bg": "#1D4ED8", "text": "#FFFFFF"},
    "red":   {"bg": "#B91C1C", "text": "#FFFFFF"},
    "green": {"bg": "#15803D", "text": "#FFFFFF"},
}
DEFAULT_ZONE = {"bg": "#4B5563", "text": "#F9FAFB"}

BG      = "#FEFEF8"
GOLD    = "#B8962E"
GOLD_LT = "#D4AF5A"
BLACK   = "#1A1A1A"
GREY    = "#6B7280"
BORDER  = "#E5E4DC"

CANVAS_W = 800
CANVAS_H = 1080


def _load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"   if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"    if bold else
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size), True
        except Exception:
            continue
    return ImageFont.load_default(), False


def _text_w(font, text: str) -> int:
    try:
        bb = font.getbbox(text)
        return bb[2] - bb[0]
    except Exception:
        return len(text) * 8   # rough fallback


def _cx(draw, y, text, font, fill):
    """Draw text horizontally centred on canvas."""
    x = (CANVAS_W - _text_w(font, text)) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _draw_corners(draw, margin=28, length=56, thick=3):
    w, h, m, ln, c = CANVAS_W, CANVAS_H, margin, length, GOLD_LT
    draw.rectangle([m,         m,         m + ln,     m + thick], fill=c)
    draw.rectangle([m,         m,         m + thick,  m + ln   ], fill=c)
    draw.rectangle([w-m-ln,    m,         w-m,        m + thick], fill=c)
    draw.rectangle([w-m-thick, m,         w-m,        m + ln   ], fill=c)
    draw.rectangle([m,         h-m-thick, m + ln,     h-m      ], fill=c)
    draw.rectangle([m,         h-m-ln,    m + thick,  h-m      ], fill=c)
    draw.rectangle([w-m-ln,    h-m-thick, w-m,        h-m      ], fill=c)
    draw.rectangle([w-m-thick, h-m-ln,    w-m,        h-m      ], fill=c)


def _hline(draw, y, colour=GOLD_LT, margin=80):
    draw.rectangle([margin, y, CANVAS_W - margin, y + 1], fill=colour)


def _badge(draw, cy, text, font, bg, fg, px=28, py=10):
    tw = _text_w(font, text)
    try:
        bb = font.getbbox(text)
        th = bb[3] - bb[1]
    except Exception:
        th = 16
    bw = tw + px * 2
    bh = th + py * 2
    x0 = (CANVAS_W - bw) // 2
    y0 = cy
    try:
        draw.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=bh // 2, fill=bg)
    except AttributeError:
        draw.rectangle([x0, y0, x0 + bw, y0 + bh], fill=bg)
    draw.text((x0 + px, y0 + py), text, font=font, fill=fg)
    return bh


def _generate_qr_image(token: str, guest_name: str, event_name: str,
                        zone: str | None = None) -> bytes:

    zk = (zone or "").lower()
    zc = ZONE_COLOURS.get(zk, DEFAULT_ZONE)
    zl = zone.upper() if zone else "GENERAL"

    # ── QR ───────────────────────────────────────────────────────────────────
    qr = qrcode.QRCode(version=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=9, border=2)
    qr.add_data(token)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=BLACK, back_color="white")
    # Extract PIL image safely
    try:
        qr_pil = qr_img.get_image().convert("RGB")
    except AttributeError:
        qr_pil = qr_img._img.convert("RGB")

    # ── Canvas ────────────────────────────────────────────────────────────────
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), color=BG)
    draw   = ImageDraw.Draw(canvas)

    # Outer border
    draw.rectangle([18, 18, CANVAS_W - 18, CANVAS_H - 18], outline=BORDER, width=1)
    _draw_corners(draw)

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_sub,  _  = _load_font(20)
    f_title, _ = _load_font(52, bold=True)
    f_conf, _  = _load_font(28, bold=True)
    f_label, _ = _load_font(20)
    f_name, _  = _load_font(32, bold=True)
    f_zone, _  = _load_font(18, bold=True)
    f_qrl, _   = _load_font(22, bold=True)
    f_foot, _  = _load_font(16)

    y = 70

    # Small subtitle (event name in grey)
    _cx(draw, y, event_name, f_sub, GREY);  y += 30
    _hline(draw, y);                         y += 14

    # Large gold title — split into ≤2 lines
    words = event_name.split()
    if len(words) > 3:
        mid   = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        _cx(draw, y, line1, f_title, GOLD); y += 68
        _cx(draw, y, line2, f_title, GOLD); y += 68
    else:
        _cx(draw, y, event_name, f_title, GOLD); y += 68

    _hline(draw, y);                               y += 18

    # "Digital Event Confirmation"
    _cx(draw, y, "Digital Event Confirmation", f_conf, BLACK); y += 52

    _hline(draw, y, colour="#D4AF5A66");            y += 24

    # Invited Name
    _cx(draw, y, "Invited Name:", f_label, GREY);   y += 32
    _cx(draw, y, guest_name, f_name, BLACK);         y += 48

    # Zone badge
    bh = _badge(draw, y, f"ZONE  {zl}", f_zone, zc["bg"], zc["text"])
    y += bh + 20

    # "QR CODE"
    _cx(draw, y, "QR CODE", f_qrl, GREY);            y += 28

    # QR image
    qr_size = 380
    qr_pil  = qr_pil.resize((qr_size, qr_size), Image.LANCZOS)
    qr_x    = (CANVAS_W - qr_size) // 2
    canvas.paste(qr_pil, (qr_x, y))
    y += qr_size + 20

    _hline(draw, y);                                 y += 20

    # "Scan at Entrance"
    _cx(draw, y, "Scan at Entrance", f_conf, BLACK); y += 50

    # Footer
    _cx(draw, CANVAS_H - 38,
        f"ID: {token[:8].upper()}  ·  Powered by Passaire", f_foot, GREY)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", quality=95)
    return buf.getvalue()


def create_ticket_qr(guest_id: str, event_id: str,
                     guest_name: str, event_name: str,
                     zone: str | None = None) -> tuple[str, str]:
    token     = str(uuid.uuid4())
    png_bytes = _generate_qr_image(token, guest_name, event_name, zone)
    file_path = f"{event_id}/{guest_id}.png"
    sb        = get_supabase()
    sb.storage.from_("tickets").upload(
        path=file_path, file=png_bytes,
        file_options={"content-type": "image/png", "upsert": "true"},
    )
    return token, sb.storage.from_("tickets").get_public_url(file_path)
