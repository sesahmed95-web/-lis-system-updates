"""
Barcode/QR generation for printed labels.

- Code 39: minimal, dependency-free generator (kept for the existing
  per-sample barcodes) -- uses only Pillow.
- Code 128: used for the English/Latin content on a visit's barcode label
  (registration number + English test codes). The bar encoding itself is
  delegated to the well-tested `python-barcode` package (correctness of a
  scanned symbol matters -- a hand-rolled table is not worth the risk), but
  the human-readable caption underneath is drawn ourselves in bold so it
  stays legible even on very small printed labels (down to ~8pt).
- QR: used for the Arabic content (patient's full name + Arabic test names),
  since Code 128 cannot represent non-Latin characters. Uses `qrcode`.

Both `python-barcode` and `qrcode` are optional at import time: if they are
ever missing (e.g. a stale offline install before the first `pip install`
picked them up), we degrade gracefully instead of crashing the print page.
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont

try:
    from barcode import Code128 as _Code128
    from barcode.writer import ImageWriter as _BarcodeImageWriter
except Exception:
    _Code128 = None
    _BarcodeImageWriter = None

try:
    import qrcode as _qrcode
except Exception:
    _qrcode = None

_HERE = os.path.dirname(os.path.abspath(__file__))
_BOLD_FONT_PATH = os.path.join(_HERE, "static", "fonts", "DejaVuSans-Bold.ttf")


def _bold_font(size):
    """Bold caption font, bundled with the project so it renders the same
    (and stays legible/clear) on any machine, not just ones that happen to
    have DejaVu Sans installed system-wide."""
    try:
        return ImageFont.truetype(_BOLD_FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

# Each character -> 9 elements (bars/spaces), 'N' = narrow, 'W' = wide.
# Order alternates bar, space, bar, space ... starting with a bar.
CODE39_PATTERNS = {
    "0": "NNNWWNWNN", "1": "WNNWNNNNW", "2": "NNWWNNNNW", "3": "WNWWNNNNN",
    "4": "NNNWWNNNW", "5": "WNNWWNNNN", "6": "NNWWWNNNN", "7": "NNNWNNWNW",
    "8": "WNNWNNWNN", "9": "NNWWNNWNN", "A": "WNNNNWNNW", "B": "NNWNNWNNW",
    "C": "WNWNNWNNN", "D": "NNNNWWNNW", "E": "WNNNWWNNN", "F": "NNWNWWNNN",
    "G": "NNNNNWWNW", "H": "WNNNNWWNN", "I": "NNWNNWWNN", "J": "NNNNWWWNN",
    "K": "WNNNNNNWW", "L": "NNWNNNNWW", "M": "WNWNNNNWN", "N": "NNNNWNNWW",
    "O": "WNNNWNNWN", "P": "NNWNWNNWN", "Q": "NNNNNNWWW", "R": "WNNNNNWWN",
    "S": "NNWNNNWWN", "T": "NNNNWNWWN", "U": "WWNNNNNNW", "V": "NWWNNNNNW",
    "W": "WWWNNNNNN", "X": "NWNNWNNNW", "Y": "WWNNWNNNN", "Z": "NWWNWNNNN",
    "-": "NWNNNNWNW", ".": "WWNNNNWNN", " ": "NWWNNNWNN", "*": "NWNNWNWNN",
}

NARROW = 2
WIDE = NARROW * 3
BAR_HEIGHT = 70


def generate_code39(text, show_text=True):
    """Return a PIL Image with a Code39 barcode for `text` (start/stop
    '*' added automatically). Only digits, uppercase letters, space, - and .
    are supported; other characters are stripped."""
    text = "".join(c for c in text.upper() if c in CODE39_PATTERNS)
    full = f"*{text}*"

    total_width = 0
    for ch in full:
        pattern = CODE39_PATTERNS[ch]
        total_width += sum(WIDE if p == "W" else NARROW for p in pattern)
        total_width += NARROW  # inter-character gap
    quiet = 20
    img_h = BAR_HEIGHT + (22 if show_text else 0)
    img = Image.new("RGB", (total_width + quiet * 2, img_h), "white")
    draw = ImageDraw.Draw(img)

    x = quiet
    for ch in full:
        pattern = CODE39_PATTERNS[ch]
        is_bar = True
        for p in pattern:
            w = WIDE if p == "W" else NARROW
            if is_bar:
                draw.rectangle([x, 0, x + w - 1, BAR_HEIGHT], fill="black")
            x += w
            is_bar = not is_bar
        x += NARROW

    if show_text:
        font = _bold_font(14)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((img.width - tw) / 2, BAR_HEIGHT + 4), text, fill="black", font=font)

    return img


def _clean_code128_text(text):
    """Code 128 subset B covers standard printable ASCII (32-126). Strip
    anything outside that range (e.g. stray Arabic) so the symbol we build
    always stays a valid, scannable barcode."""
    cleaned = "".join(ch for ch in (text or "") if 32 <= ord(ch) <= 126)
    return cleaned.strip() or "-"


def generate_code128(text, show_text=True, caption=None):
    """Return a PIL Image with a Code128 barcode for the given English/Latin
    `text` (registration number + English test codes, typically). A bold,
    high-contrast human-readable caption is drawn underneath -- kept
    legible even when the printed label is tiny (down to ~8pt), which is
    why it is rendered with our own bundled bold font rather than relying
    on whatever default font the barcode library ships with."""
    payload = _clean_code128_text(text)
    caption_text = _clean_code128_text(caption) if caption is not None else payload

    if _Code128 is None:
        # Optional dependency missing -- degrade instead of crashing the
        # print page (Code 39 covers the same alphanumeric range).
        return generate_code39(payload, show_text=show_text)

    try:
        symbol = _Code128(payload, writer=_BarcodeImageWriter())
        buf = io.BytesIO()
        symbol.write(buf, options={
            "module_width": 0.32,
            "module_height": 16.0,
            "quiet_zone": 4.0,
            "write_text": False,
            "dpi": 300,
        })
        buf.seek(0)
        bars_img = Image.open(buf).convert("RGB")
    except Exception:
        return generate_code39(payload, show_text=show_text)

    if not show_text:
        return bars_img

    font = _bold_font(20)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    bbox = probe.textbbox((0, 0), caption_text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad_top = 8
    out_w = max(bars_img.width, text_w + 24)
    out_h = bars_img.height + pad_top + text_h + 10
    out = Image.new("RGB", (out_w, out_h), "white")
    out.paste(bars_img, ((out_w - bars_img.width) // 2, 0))
    draw = ImageDraw.Draw(out)
    draw.text(((out_w - text_w) / 2, bars_img.height + pad_top), caption_text,
               fill="black", font=font)
    return out


def generate_qr(data, box_size=6, border=2):
    """Return a PIL Image QR code for `data`. QR is used (instead of
    Code128) for content that can include Arabic text -- e.g. the patient's
    full name and Arabic test names -- since Code128 cannot represent
    non-Latin characters, while a QR code encodes UTF-8 natively and can be
    read with any phone camera."""
    data = (data or "").strip()
    if _qrcode is not None and data:
        try:
            qr = _qrcode.QRCode(
                version=None,
                error_correction=_qrcode.constants.ERROR_CORRECT_M,
                box_size=box_size,
                border=border,
            )
            qr.add_data(data)
            qr.make(fit=True)
            return qr.make_image(fill_color="black", back_color="white").convert("RGB")
        except Exception:
            pass  # fall through to the placeholder below

    # Optional dependency missing, nothing to encode, or generation failed
    # for any reason -- draw a plain placeholder box instead of crashing
    # the print page.
    img = Image.new("RGB", (160, 160), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 159, 159], outline="black", width=2)
    return img
