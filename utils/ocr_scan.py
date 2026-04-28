"""OCR scanning for paper reports — extracts product name + quantity from images."""

import re
from database.db import get_session
from database.models import Product, ProductStatus


def _ocr_text(image_path: str) -> str:
    """Extract raw text from an image using pytesseract. Raises RuntimeError if unavailable."""
    try:
        import pytesseract
        from PIL import Image, ImageFilter, ImageEnhance

        img = Image.open(image_path).convert("L")        # grayscale
        img = ImageEnhance.Contrast(img).enhance(2.0)     # boost contrast
        img = img.filter(ImageFilter.SHARPEN)

        # Try Spanish, fall back to English
        try:
            text = pytesseract.image_to_string(img, lang="spa", config="--psm 6")
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(img, config="--psm 6")
        return text
    except ImportError:
        raise RuntimeError(
            "pytesseract no está instalado.\nEjecuta: pip install pytesseract"
        )
    except Exception as exc:
        msg = str(exc)
        if "tesseract" in msg.lower() or "not found" in msg.lower() or "win32" in msg.lower():
            raise RuntimeError(
                "Tesseract OCR no está instalado en el sistema.\n"
                "Descárgalo desde: https://github.com/UB-Mannheim/tesseract/wiki\n"
                "Instálalo y reinicia la aplicación."
            )
        raise RuntimeError(f"Error al procesar la imagen: {exc}")


def _find_product(name: str, prod_by_name: dict):
    """Find product by exact, then partial word match."""
    nl = name.lower().strip()
    if nl in prod_by_name:
        return prod_by_name[nl]
    # substring match
    for pname, prod in prod_by_name.items():
        if nl in pname or pname in nl:
            return prod
    # word-overlap match (at least 2 words or 50% overlap)
    words = set(nl.split())
    for pname, prod in prod_by_name.items():
        pwords = set(pname.split())
        if words and pwords:
            overlap = len(words & pwords)
            if overlap >= 2 or (overlap >= 1 and overlap / min(len(words), len(pwords)) >= 0.5):
                return prod
    return None


def _parse_lines(lines: list[str], prod_by_name: dict) -> tuple[list, list]:
    """Parse text lines into (rows, parse_errors). Each row: product + qty."""
    rows = []
    parse_errors = []

    for line in lines:
        line = line.strip()
        if not line or len(line) < 2:
            continue

        # Skip obvious header/title lines (all caps, no digits)
        if not re.search(r"\d", line):
            continue

        # Pattern A: "Product Name: 5" or "Product Name 5"  (number at END)
        m = re.match(r"^(.+?)\s*[:\-\|]?\s+(\d+)\s*$", line)
        if m:
            name, qty_str = m.group(1).strip(), m.group(2)
        else:
            # Pattern B: "5 Product Name"  (number at START)
            m2 = re.match(r"^(\d+)\s+(.+)$", line)
            if m2:
                qty_str, name = m2.group(1), m2.group(2).strip()
            else:
                continue  # no number found, skip silently

        # Remove trailing punctuation from name
        name = re.sub(r"[\.,:;\-]+$", "", name).strip()

        try:
            qty = int(qty_str)
        except ValueError:
            parse_errors.append(f"Cantidad inválida en: «{line}»")
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
    OCR an image and extract product+quantity rows.
    Returns:
      {
        "rows": [{"product_id", "name", "ocr_name", "qty_remove",
                  "current_stock", "remaining", "error"}],
        "parse_errors": [str],
        "raw_text": str,
      }
    Raises RuntimeError if OCR engine is unavailable.
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
