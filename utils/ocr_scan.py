"""OCR scanning — uses OCR.space API (iOS/macOS/Windows)
   Falls back to local Tesseract if no API key configured (desktop only)."""

import base64
import re
from database.db import get_session
from database.models import Product, ProductStatus


def _ocr_with_ocrspace(image_path: str, api_key: str) -> str:
    try:
        import requests
    except ImportError:
        raise RuntimeError("Instala 'requests': pip install requests")

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    ext = image_path.rsplit(".", 1)[-1].lower()
    fmt_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "bmp": "image/bmp", "tiff": "image/tiff", "tif": "image/tiff",
        "webp": "image/webp",
    }
    mime = fmt_map.get(ext, "image/jpeg")

    payload = {
        "apikey": api_key,
        "base64Image": f"data:{mime};base64,{img_b64}",
        "language": "spa",
        "isOverlayRequired": False,
        "detectOrientation": True,
        "scale": True,
        "OCREngine": 2,  # Engine 2 = mejor para texto impreso
    }

    resp = requests.post(
        "https://api.ocr.space/parse/image",
        data=payload,
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OCR.space error {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    if data.get("IsErroredOnProcessing"):
        err = data.get("ErrorMessage", ["Error desconocido"])
        raise RuntimeError(f"OCR.space: {err[0] if isinstance(err, list) else err}")

    results = data.get("ParsedResults", [])
    return "\n".join(r.get("ParsedText", "") for r in results) if results else ""


def _ocr_with_tesseract(image_path: str) -> str:
    """Fallback local — solo funciona en desktop con Tesseract instalado."""
    try:
        import pytesseract
        from PIL import Image, ImageFilter, ImageEnhance
    except ImportError:
        raise RuntimeError("pytesseract no está instalado.")
    img = Image.open(image_path).convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)
    try:
        return pytesseract.image_to_string(img, lang="spa", config="--psm 6")
    except Exception:
        return pytesseract.image_to_string(img, config="--psm 6")


def _ocr_text(image_path: str) -> str:
    """Elige el mejor backend OCR disponible."""
    try:
        from config import OCR_SPACE_API_KEY
        api_key = OCR_SPACE_API_KEY
    except ImportError:
        api_key = ""

    if api_key and api_key.strip():
        return _ocr_with_ocrspace(image_path, api_key.strip())

    # Fallback: Tesseract local (solo desktop)
    try:
        return _ocr_with_tesseract(image_path)
    except RuntimeError:
        raise RuntimeError(
            "No hay OCR configurado.\n\n"
            "Obtén una API key gratis en:\n"
            "  https://ocr.space/ocrapi/freekey\n\n"
            "Luego pégala en config.py → OCR_SPACE_API_KEY"
        )


# ── Matching de productos ──────────────────────────────────────

def _find_product(name: str, prod_by_name: dict):
    nl = name.lower().strip()
    if nl in prod_by_name:
        return prod_by_name[nl]
    for pname, prod in prod_by_name.items():
        if nl in pname or pname in nl:
            return prod
    words = set(nl.split())
    for pname, prod in prod_by_name.items():
        pwords = set(pname.split())
        if words and pwords:
            overlap = len(words & pwords)
            if overlap >= 2 or (overlap >= 1 and overlap / min(len(words), len(pwords)) >= 0.5):
                return prod
    return None


def _parse_lines(lines, prod_by_name):
    rows, parse_errors = [], []
    for line in lines:
        line = line.strip()
        if not line or len(line) < 2 or not re.search(r"\d", line):
            continue
        # Patrón A: "Nombre: 5" o "Nombre 5" (número al final)
        m = re.match(r"^(.+?)\s*[:\-\|]?\s+(\d+)\s*$", line)
        if m:
            name, qty_str = m.group(1).strip(), m.group(2)
        else:
            # Patrón B: "5 Nombre" (número al inicio)
            m2 = re.match(r"^(\d+)\s+(.+)$", line)
            if m2:
                qty_str, name = m2.group(1), m2.group(2).strip()
            else:
                continue
        name = re.sub(r"[\.,:;\-]+$", "", name).strip()
        try:
            qty = int(qty_str)
        except ValueError:
            parse_errors.append(f"Cantidad inválida: «{line}»")
            continue
        if qty <= 0:
            continue
        prod = _find_product(name, prod_by_name)
        if prod:
            remaining = prod.stock - qty
            rows.append({
                "product_id": prod.id,
                "name": prod.name,
                "ocr_name": name,
                "qty_remove": qty,
                "current_stock": prod.stock,
                "remaining": remaining,
                "error": "Stock insuficiente" if remaining < 0 else None,
            })
        else:
            rows.append({
                "product_id": None,
                "name": name,
                "ocr_name": name,
                "qty_remove": qty,
                "current_stock": None,
                "remaining": None,
                "error": "Producto no encontrado en el inventario",
            })
    return rows, parse_errors


def parse_report_image(image_path: str) -> dict:
    """
    OCR una imagen y extrae filas producto+cantidad.
    Devuelve: {"rows": [...], "parse_errors": [...], "raw_text": str}
    Lanza RuntimeError si no hay OCR disponible.
    """
    raw_text = _ocr_text(image_path)
    lines = raw_text.splitlines()
    session = get_session()
    try:
        products = session.query(Product).filter(
            Product.status == ProductStatus.ACTIVE
        ).all()
        prod_by_name = {p.name.lower(): p for p in products}
    finally:
        session.close()
    rows, parse_errors = _parse_lines(lines, prod_by_name)
    return {"rows": rows, "parse_errors": parse_errors, "raw_text": raw_text}
