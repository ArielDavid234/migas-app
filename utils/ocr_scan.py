"""OCR scanning — uses OCR.space API (iOS/macOS/Windows)
   Falls back to local Tesseract if no API key configured (desktop only)."""

import base64
import re
from database.db import get_session
from database.models import Product, ProductStatus


_OCR_MAX_BYTES = 1_400_000  # OCR.space free plan limit is 1.5 MB; use 1.4 MB to be safe


def _compress_image_bytes(raw: bytes) -> tuple:
    """Return (bytes, mime) compressed to fit within OCR.space free-plan limit.
    Tries JPEG quality reduction first, then dimension scaling.
    Falls back to original bytes if Pillow is unavailable.
    """
    if len(raw) <= _OCR_MAX_BYTES:
        return raw, None  # no compression needed; caller keeps original mime

    try:
        import io
        from PIL import Image
    except ImportError:
        return raw, None  # can't compress without Pillow

    img = Image.open(io.BytesIO(raw)).convert("RGB")

    # 1. Try quality reduction only (keeps full resolution)
    for quality in (85, 75, 65, 55, 45):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= _OCR_MAX_BYTES:
            return buf.getvalue(), "image/jpeg"

    # 2. Scale down dimensions progressively
    scale = 0.8
    while scale >= 0.3:
        w, h = img.size
        resized = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=65, optimize=True)
        if buf.tell() <= _OCR_MAX_BYTES:
            return buf.getvalue(), "image/jpeg"
        scale -= 0.15

    return raw, None  # give up; API will return 413


def _ocrspace_request(image_path: str, api_key: str, *, language: str = "spa", overlay: bool = False) -> dict:
    try:
        import requests
    except ImportError:
        raise RuntimeError("Instala 'requests': pip install requests")

    with open(image_path, "rb") as f:
        raw_bytes = f.read()

    compressed, compressed_mime = _compress_image_bytes(raw_bytes)

    ext = image_path.rsplit(".", 1)[-1].lower()
    fmt_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "bmp": "image/bmp", "tiff": "image/tiff", "tif": "image/tiff",
        "webp": "image/webp",
    }
    mime = compressed_mime or fmt_map.get(ext, "image/jpeg")
    img_b64 = base64.b64encode(compressed).decode("utf-8")

    payload = {
        "apikey": api_key,
        "base64Image": f"data:{mime};base64,{img_b64}",
        "language": language,
        "isOverlayRequired": overlay,
        "detectOrientation": True,
        "OCREngine": 2,  # Engine 2 = mejor para texto impreso
    }

    import time as _time
    last_exc: Exception | None = None
    for _attempt in range(3):
        try:
            resp = requests.post(
                "https://api.ocr.space/parse/image",
                data=payload,
                timeout=60,
            )
            if resp.status_code in (502, 503, 504):
                last_exc = RuntimeError(f"OCR.space error {resp.status_code} (intento {_attempt + 1}/3)")
                _time.sleep(3 * (_attempt + 1))
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"OCR.space error {resp.status_code}: {resp.text[:200]}")
            break
        except requests.exceptions.ConnectionError as exc:
            last_exc = RuntimeError(f"Sin conexión con OCR.space (intento {_attempt + 1}/3): {exc}")
            _time.sleep(3 * (_attempt + 1))
    else:
        raise last_exc

    data = resp.json()
    if data.get("IsErroredOnProcessing"):
        err = data.get("ErrorMessage", ["Error desconocido"])
        raise RuntimeError(f"OCR.space: {err[0] if isinstance(err, list) else err}")

    return data


def _ocr_with_ocrspace(image_path: str, api_key: str) -> str:
    data = _ocrspace_request(image_path, api_key, language="spa", overlay=False)

    results = data.get("ParsedResults", [])
    return "\n".join(r.get("ParsedText", "") for r in results) if results else ""


def _ocr_with_ocrspace_overlay(image_path: str, api_key: str) -> dict:
    data = _ocrspace_request(image_path, api_key, language="eng", overlay=True)

    results = data.get("ParsedResults", [])
    raw_text = "\n".join(r.get("ParsedText", "") for r in results) if results else ""
    overlay_words = []

    for result in results:
        overlay = result.get("TextOverlay") or {}
        for line in overlay.get("Lines", []) or []:
            for word in line.get("Words", []) or []:
                text = str(word.get("WordText", "") or "").strip()
                if not text:
                    continue
                overlay_words.append({
                    "text": text,
                    "left": int(word.get("Left", 0) or 0),
                    "top": int(word.get("Top", 0) or 0),
                })

    return {"raw_text": raw_text, "overlay_words": overlay_words}


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


# ── Department Report Parser ──────────────────────────────────

def _parse_decimal(s: str) -> float:
    """Handle decimal values with period or comma as decimal separator."""
    s = s.strip()
    comma_count = s.count(',')
    dot_count = s.count('.')
    try:
        if comma_count == 1 and dot_count == 0:
            # European decimal: "114,08" → 114.08
            return float(s.replace(',', '.'))
        elif dot_count == 1 and comma_count == 0:
            return float(s)
        elif comma_count == 1 and dot_count == 1:
            if s.index(',') < s.index('.'):
                # "1,234.56" → thousands separator
                return float(s.replace(',', ''))
            else:
                # "1.234,56" → European thousands + decimal
                return float(s.replace('.', '').replace(',', '.'))
        else:
            return float(s.replace(',', ''))
    except (ValueError, IndexError):
        return 0.0


def _normalize_word_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _normalize_field_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("|", " ")).strip()


def _clean_numeric_text(text: str) -> str:
    normalized = _normalize_field_text(text)
    tokens = re.findall(r"\d+", normalized)
    if tokens and not any(separator in normalized for separator in [",", ".", ":"]):
        if len(tokens) == 2 and len(tokens[1]) <= 2:
            return f"{tokens[0]}.{tokens[1].zfill(2)}"

    cleaned = normalized.replace(" ", "")
    cleaned = cleaned.replace(":", ".")
    cleaned = re.sub(r"[^\d,\.\-]", "", cleaned)
    return cleaned.strip(".,")


def _parse_money_text(text: str):
    cleaned = _clean_numeric_text(text)
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    return _parse_decimal(cleaned)


def _parse_items_text(text: str):
    normalized = _normalize_field_text(text)
    matches = re.findall(r"\d+(?:[.,:]\d+)?", normalized)
    if matches:
        value = _parse_decimal(matches[0].replace(":", "."))
        rounded = int(round(value))
        return rounded if abs(value - rounded) <= 0.25 else int(value)

    value = _parse_money_text(text)
    if value is None:
        m = re.search(r"\d+", str(text or ""))
        return int(m.group()) if m else None
    rounded = int(round(value))
    return rounded if abs(value - rounded) <= 0.25 else int(value)


def _parse_dept_text(text: str):
    matches = re.findall(r"\d{1,4}", str(text or ""))
    return matches[-1] if matches else ""


def _cluster_overlay_words(words: list, y_threshold: int = 8) -> list:
    clusters = []
    for word in sorted(words, key=lambda item: (item["top"], item["left"])):
        if not clusters or abs(word["top"] - clusters[-1]["top"]) > y_threshold:
            clusters.append({"top": word["top"], "words": [word]})
            continue
        clusters[-1]["words"].append(word)
        tops = [w["top"] for w in clusters[-1]["words"]]
        clusters[-1]["top"] = int(sum(tops) / len(tops))

    for cluster in clusters:
        cluster["words"].sort(key=lambda item: item["left"])
        cluster["text"] = " ".join(_normalize_word_text(w["text"]) for w in cluster["words"] if _normalize_word_text(w["text"]))
    return clusters


def _find_report_header_positions(clusters: list) -> tuple:
    start_idx = None
    positions = {}

    for index, cluster in enumerate(clusters):
        text_up = cluster["text"].upper()
        if start_idx is None and "DEPARTMENT" in text_up and "REPORT" in text_up:
            start_idx = index
            continue
        if start_idx is None:
            continue

        for word in cluster["words"]:
            word_up = word["text"].upper()
            if word_up.startswith("DEPT") and "dept" not in positions:
                positions["dept"] = word["left"]
            elif word_up == "DESCRIPTION" and "desc" not in positions:
                positions["desc"] = word["left"]
            elif word_up == "GROSS" and "desc" not in positions:
                positions["desc"] = word["left"]
            elif word_up == "REFUNDS" and "refunds" not in positions:
                positions["refunds"] = word["left"]
            elif word_up in {"ITEMS", "DISCOUNTS"} and "mid" not in positions:
                positions["mid"] = word["left"]
            elif word_up == "NET" and "right" not in positions:
                positions["right"] = word["left"]

        if len(positions) >= 5:
            break

    return start_idx, positions


def _build_report_column_bounds(positions: dict) -> dict:
    dept_x = positions.get("dept", 0)
    desc_x = positions.get("desc", dept_x + 35)
    refunds_x = positions.get("refunds", desc_x + 60)
    mid_x = positions.get("mid", refunds_x + 55)
    right_x = positions.get("right", mid_x + 50)

    return {
        "dept_desc": int((dept_x + desc_x) / 2),
        "desc_mid": int((desc_x + mid_x) / 2),
        "desc_refunds": int((desc_x + refunds_x) / 2),
        "refunds_mid": int((refunds_x + mid_x) / 2),
        "mid_right": int((mid_x + right_x) / 2),
    }


def _cluster_header_columns(cluster: dict, bounds: dict) -> dict:
    columns = {"dept": [], "left": [], "mid": [], "right": []}
    for word in cluster["words"]:
        left = word["left"]
        if left < bounds["dept_desc"]:
            columns["dept"].append(word["text"])
        elif left < bounds["desc_mid"]:
            columns["left"].append(word["text"])
        elif left < bounds["mid_right"]:
            columns["mid"].append(word["text"])
        else:
            columns["right"].append(word["text"])

    return {
        key: _normalize_field_text(" ".join(values))
        for key, values in columns.items()
    }


def _cluster_detail_columns(cluster: dict, bounds: dict) -> dict:
    columns = {"dept": [], "left": [], "refunds": [], "mid": [], "right": []}
    for word in cluster["words"]:
        left = word["left"]
        if left < bounds["dept_desc"]:
            columns["dept"].append(word["text"])
        elif left < bounds["desc_refunds"]:
            columns["left"].append(word["text"])
        elif left < bounds["refunds_mid"]:
            columns["refunds"].append(word["text"])
        elif left < bounds["mid_right"]:
            columns["mid"].append(word["text"])
        else:
            columns["right"].append(word["text"])

    return {
        key: _normalize_field_text(" ".join(values))
        for key, values in columns.items()
    }


def _is_report_header_or_footer(text: str) -> bool:
    text_up = text.upper()
    if not text_up:
        return True
    if any(token in text_up for token in ["DEPARTMENT REPORT", "DEPTS", "DESCRIPTION", "REFUNDS", "DISCOUNTS", "NET SALES", "GROSS"]):
        return True
    if re.search(r"^(NEG\s+DEPTS?|OTHER\s+DEPTS?|TOTAL|LOYALTY|STATION\s+TOTAL)", text_up):
        return True
    return False


def _looks_like_row_header(columns: dict) -> bool:
    left = columns["left"]
    return bool(re.search(r"[A-Z]", left, re.IGNORECASE))


def _parse_items_from_percent_block(text: str):
    normalized = _normalize_field_text(text)
    if "%" not in normalized:
        return None
    matches = re.findall(r"\d+(?:[.,:]\d+)?", normalized)
    if len(matches) < 2:
        return None
    value = _parse_decimal(matches[0].replace(":", "."))
    rounded = int(round(value))
    return rounded if abs(value - rounded) <= 0.25 else int(value)


def _looks_like_row_detail(columns: dict) -> bool:
    gross = _parse_money_text(columns["left"])
    if gross is None and "." in columns.get("dept", ""):
        gross = _parse_money_text(columns["dept"])
    return gross is not None and any(
        _parse_money_text(columns[key]) is not None for key in ("refunds", "mid", "right")
    )


def _fill_missing_dept_numbers(rows: list):
    explicit = []
    for index, row in enumerate(rows):
        dept = row.get("dept_num", "")
        explicit.append((index, int(dept))) if str(dept).isdigit() else None

    if not explicit:
        return rows

    first_index, first_value = explicit[0]
    if first_index > 0:
        start_value = max(1, first_value - first_index)
        for idx in range(first_index):
            rows[idx]["dept_num"] = str(start_value + idx)

    for current, nxt in zip(explicit, explicit[1:]):
        cur_index, cur_value = current
        next_index, next_value = nxt
        gap_rows = next_index - cur_index - 1
        if gap_rows <= 0:
            continue
        for offset in range(1, gap_rows + 1):
            candidate = cur_value + offset
            if candidate >= next_value:
                break
            rows[cur_index + offset]["dept_num"] = str(candidate)

    last_index, last_value = explicit[-1]
    for idx in range(last_index + 1, len(rows)):
        if not rows[idx].get("dept_num"):
            rows[idx]["dept_num"] = str(last_value + (idx - last_index))

    return rows


def _parse_dept_report_overlay_words(overlay_words: list) -> tuple:
    rows = []
    parse_errors = []
    clusters = _cluster_overlay_words(overlay_words)
    start_idx, positions = _find_report_header_positions(clusters)

    if start_idx is None or len(positions) < 4:
        return rows, ["No se pudo identificar la cabecera del DEPARTMENT REPORT"]

    bounds = _build_report_column_bounds(positions)
    pending = None

    for cluster in clusters[start_idx + 1:]:
        text = _normalize_field_text(cluster["text"])
        if not text:
            continue
        text_up = text.upper()
        if re.search(r"^(NEG\s+DEPTS?|OTHER\s+DEPTS?|TOTAL|LOYALTY|STATION\s+TOTAL)", text_up):
            break
        if _is_report_header_or_footer(text):
            continue

        header_columns = _cluster_header_columns(cluster, bounds)

        if _looks_like_row_header(header_columns):
            if pending:
                parse_errors.append(
                    f"Fila incompleta para depto {pending.get('dept_num') or '?'} ({pending.get('description') or 'sin descripcion'})"
                )
                rows.append(pending)

            pending = {
                "dept_num": _parse_dept_text(header_columns["dept"]),
                "description": header_columns["left"],
                "items": (
                    _parse_items_text(header_columns["mid"])
                    or _parse_items_from_percent_block(header_columns["right"])
                    or 0
                ),
                "sales_gross": 0.0,
                "refunds": 0.0,
                "discounts": 0.0,
                "net_sales": 0.0,
            }
            continue

        detail_columns = _cluster_detail_columns(cluster, bounds)
        if pending and _looks_like_row_detail(detail_columns):
            gross_value = _parse_money_text(detail_columns["left"])
            if gross_value is None and "." in detail_columns.get("dept", ""):
                gross_value = _parse_money_text(detail_columns["dept"])
            pending["sales_gross"] = gross_value or 0.0
            pending["refunds"] = _parse_money_text(detail_columns["refunds"]) or 0.0
            pending["discounts"] = _parse_money_text(detail_columns["mid"]) or 0.0
            pending["net_sales"] = _parse_money_text(detail_columns["right"]) or 0.0
            rows.append(pending)
            pending = None

    if pending:
        parse_errors.append(
            f"Fila incompleta para depto {pending.get('dept_num') or '?'} ({pending.get('description') or 'sin descripcion'})"
        )
        rows.append(pending)

    cleaned_rows = []
    for row in rows:
        if not row.get("description"):
            continue
        cleaned_rows.append({
            "dept_num": str(row.get("dept_num", "") or ""),
            "description": row.get("description", "").strip(),
            "items": int(row.get("items") or 0),
            "sales_gross": float(row.get("sales_gross") or 0.0),
            "refunds": float(row.get("refunds") or 0.0),
            "discounts": float(row.get("discounts") or 0.0),
            "net_sales": float(row.get("net_sales") or 0.0),
        })

    return _fill_missing_dept_numbers(cleaned_rows), parse_errors


def _parse_dept_report_lines(lines: list) -> tuple:
    """
    Parse DEPARTMENT REPORT format (2 lines per department):
      Line 1: DEPT#  DESCRIPTION  ITEMS  [%OF]
      Line 2: GROSS  REFUNDS  DISCOUNTS  NET_SALES
    Returns (rows, parse_errors).
    """
    rows = []
    parse_errors = []

    in_report = False
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if re.search(r'DEPARTMENT\s*REPORT', line, re.IGNORECASE):
            in_report = True
            i += 1
            continue

        if not in_report:
            i += 1
            continue

        # Skip empty lines and column-header lines
        if not line:
            i += 1
            continue
        if re.search(r'DEPT\s*#|DESCRIPTION|GROSS\s+REFUNDS|NET\s+SALES', line, re.IGNORECASE):
            i += 1
            continue

        # Stop at footer totals
        if re.match(r'^(NEG\s+DEPTS?|OTHER\s+DEPTS?|TOTAL|LOYALTY|STATION\s+TOTAL)', line, re.IGNORECASE):
            break

        # Match dept info line: starts with dept# (1–4 digits), then name, then items (integer)
        m = re.match(
            r'^(\d{1,4})\s+([A-Z][A-Z0-9 &\-\.\/]*?)\s+(\d+)\b',
            line, re.IGNORECASE
        )
        if m:
            dept_num = m.group(1)
            description = m.group(2).strip()
            try:
                items = int(m.group(3))
            except ValueError:
                items = 0

            # Find next non-empty line for the money values
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                money_parts = re.findall(r'\d+[.,]\d+', lines[j].strip())
                if len(money_parts) >= 4:
                    rows.append({
                        "dept_num": dept_num,
                        "description": description,
                        "items": items,
                        "sales_gross": _parse_decimal(money_parts[0]),
                        "refunds": _parse_decimal(money_parts[1]),
                        "discounts": _parse_decimal(money_parts[2]),
                        "net_sales": _parse_decimal(money_parts[3]),
                    })
                    i = j + 1
                    continue
                else:
                    parse_errors.append(
                        f"Dept {dept_num} ({description}): no se encontró la línea de valores"
                    )
        i += 1

    return rows, parse_errors


# ── PLU Sales Report Parser ───────────────────────────────────

def _is_plu_sales_report(raw_text: str) -> bool:
    """Detect PLU Sales Report format (vs. old DEPARTMENT REPORT).

    Handles both title pages (contain 'PLU SALES REPORT') and continuation
    pages that may only repeat the column headers or just show data rows with
    long PLU item codes (8-15 digits).
    """
    t = raw_text.upper()
    if "PLU SALES REPORT" in t:
        return True
    # Column headers present — no strict requirement for "PLU" keyword, since
    # continuation pages often don't repeat the report title and OCR can
    # mis-read "PLU NO." on the column header line.
    if "COUNT" in t and "PRICE" in t and ("DESCRIPTION" in t or "DEPARTMENT" in t):
        return True
    if "COUNT" in t and "PRICE" in t and "SALES" in t:
        return True
    # Continuation pages: PLU item codes (6+ digits) + at least one numeric column header
    if re.search(r"\b\d{6,15}\b", raw_text) and ("COUNT" in t or "PRICE" in t):
        return True
    # Headerless continuation pages: 2+ lines that start with a long PLU item code.
    # DEPT reports only use 1-4 digit dept numbers, so 6+ digit line-starters
    # are a uniquely strong PLU signal even without any keyword markers.
    if len(re.findall(r"(?m)^\d{6,}", raw_text)) >= 2:
        return True
    return False


def _find_plu_header_positions(clusters: list) -> tuple:
    """Find column x-positions from the PLU Sales Report column header row.
    Returns (header_idx, positions_dict) with keys:
      plu, pkg, desc, dept, count, price, sales, pct_dept, pct_total.

    Many POS printers use a two-line column header where '% OF' appears on
    the line above (or below) the DESCRIPTION/COUNT/PRICE line.  After finding
    the main header cluster we scan ±2 adjacent clusters for the missing
    pct_dept / pct_total positions.
    """
    for index, cluster in enumerate(clusters):
        text_up = cluster["text"].upper()
        # The column header row unambiguously contains DESCRIPTION and
        # at least one of COUNT or PRICE.
        if "DESCRIPTION" not in text_up:
            continue
        if "COUNT" not in text_up and "PRICE" not in text_up:
            continue

        positions = {}
        for word in cluster["words"]:
            word_up = word["text"].upper().strip(".,;:!")
            left = word["left"]
            if word_up.startswith("PLU") and not word_up[3:4].isalpha() and "plu" not in positions:
                positions["plu"] = left
            elif word_up.startswith("PKG") and "pkg" not in positions:
                positions["pkg"] = left
            elif word_up == "DESCRIPTION" and "desc" not in positions:
                positions["desc"] = left
            elif word_up == "DEPARTMENT" and "dept" not in positions:
                positions["dept"] = left
            elif word_up == "COUNT" and "count" not in positions:
                positions["count"] = left
            elif word_up == "PRICE" and "price" not in positions:
                positions["price"] = left
            elif word_up == "SALES" and "sales" not in positions:
                positions["sales"] = left
            elif word_up == "%":
                if "pct_dept" not in positions:
                    positions["pct_dept"] = left
                elif "pct_total" not in positions and abs(left - positions.get("pct_dept", 0)) > 10:
                    positions["pct_total"] = left

        if len(positions) < 4:
            continue

        # ── Two-line header: look at up to 2 adjacent clusters (before and
        #    after this one) for the missing % OF DEPT / % OF TOTAL markers.
        #    We skip any adjacent cluster that contains a long PLU item number
        #    (6+ consecutive digits) to avoid picking up data-row words.
        if "pct_dept" not in positions or "pct_total" not in positions:
            _adj_range = (
                list(range(max(0, index - 2), index))
                + list(range(index + 1, min(len(clusters), index + 3)))
            )
            for _adj_idx in _adj_range:
                adj_text_up = clusters[_adj_idx]["text"].upper()
                if re.search(r"\d{6,}", adj_text_up):  # data row → stop looking
                    continue
                for word in clusters[_adj_idx]["words"]:
                    word_up = word["text"].upper().strip(".,;:!")
                    left = word["left"]
                    if word_up == "%":
                        if "pct_dept" not in positions:
                            positions["pct_dept"] = left
                        elif "pct_total" not in positions and abs(left - positions.get("pct_dept", 0)) > 10:
                            positions["pct_total"] = left
                    # Lone "DEPT" or "DEPT." well past the SALES column → pct_dept
                    elif word_up in ("DEPT", "DEPT.") and "pct_dept" not in positions:
                        _sales_x = positions.get("sales", positions.get("price", 0))
                        if left > _sales_x + 15:
                            positions["pct_dept"] = left
                    # Lone "TOTAL" well past pct_dept → pct_total
                    elif word_up == "TOTAL" and "pct_total" not in positions:
                        _ref_x = positions.get("pct_dept", positions.get("sales", 0))
                        if left > _ref_x + 15:
                            positions["pct_total"] = left
                if "pct_dept" in positions and "pct_total" in positions:
                    break

        # Shift column boundaries leftward to absorb OCR pixel noise and
        # right-alignment overhang.  Applied AFTER all positions are collected.
        _shift_map = {
            "dept":       5,
            "count":     10,
            "price":     10,
            "sales":     10,
            "pct_dept":  10,
            "pct_total": 10,
        }
        _prev_x = positions.get("desc", 0)
        for _col in ["dept", "count", "price", "sales", "pct_dept", "pct_total"]:
            if _col in positions:
                positions[_col] = max(_prev_x + 5, positions[_col] - _shift_map[_col])
                _prev_x = positions[_col]
        return index, positions

    return None, {}


_PLU_COL_ORDER = ["plu", "pkg", "desc", "dept", "count", "price", "sales", "pct_dept", "pct_total"]

# Regexes for format-based (headerless) row parsing
_PLU_CODE_RE  = re.compile(r"^\d{6,15}$")
_MONEY_VAL_RE = re.compile(r"^\$?\d{1,6}(?:[.,]\d{1,2})?$")
_PCT_VAL_RE   = re.compile(r"^\d{1,3}(?:[.,]\d{1,2})?%?$")
_INT_VAL_RE   = re.compile(r"^\d{1,4}$")


def _parse_plu_row_by_format(cluster: dict) -> "dict | None":
    """Parse one PLU data row by value format (right-to-left).

    Works without column header positions — suitable for headerless continuation
    pages.  Column order (fixed by POS printer):
      [PLU No.] [Pkg Qty] Description Department Count Price Sales %Dept %Total
    Leading pure-digit words (PLU code / pkg qty) are skipped automatically
    if present, but are NOT required.  Numeric columns are identified from
    the right by their value format.
    """
    words = [w for w in cluster["words"] if _normalize_word_text(w["text"])]
    if len(words) < 3:  # minimum: at least description + price + sales
        return None
    raw_texts = [_normalize_word_text(w["text"]) for w in words]

    # ── Preprocess: merge split OCR tokens ──────────────────────────────────
    # OCR often outputs "$ 4.89" as two words ('$','4.89') and
    # "5.25 %" as two words ('5.25','%').  Merge them before parsing.
    texts: list = []
    idx = 0
    while idx < len(raw_texts):
        t = raw_texts[idx]
        if t == "$" and idx + 1 < len(raw_texts) and re.match(r"^\d", raw_texts[idx + 1]):
            texts.append("$" + raw_texts[idx + 1])
            idx += 2
        elif t not in ("$", "%") and idx + 1 < len(raw_texts) and raw_texts[idx + 1] == "%":
            texts.append(t + "%")
            idx += 2
        else:
            texts.append(t)
            idx += 1
    # ────────────────────────────────────────────────────────────────────────

    # Optionally skip leading PLU code (4+ digits) and pkg qty (1-2 digits).
    start = 0
    if re.match(r"^\d{4,}$", texts[start]):   # PLU code: 4+ digit string
        start += 1
        if start < len(texts) and re.match(r"^\d{1,2}$", texts[start]):
            start += 1  # pkg qty

    if len(texts) - start < 3:
        return None  # too few words after skipping leading codes

    right = len(texts) - 1
    pct_total = pct_dept = sales_str = price_str = count_str = ""

    # Parse right-to-left: %total, %dept, sales, price, count
    if right >= start and _PCT_VAL_RE.match(texts[right]):
        pct_total = texts[right]; right -= 1
    if right >= start and _PCT_VAL_RE.match(texts[right]):
        pct_dept = texts[right]; right -= 1
    if right >= start and _MONEY_VAL_RE.match(texts[right]):
        sales_str = texts[right]; right -= 1
    if right >= start and _MONEY_VAL_RE.match(texts[right]):
        price_str = texts[right]; right -= 1
    if right >= start and _INT_VAL_RE.match(texts[right]):
        count_str = texts[right]; right -= 1

    if not price_str and not sales_str:
        return None  # No numeric columns found — not a data row

    # Middle words (start..right inclusive): Description + Department
    middle = texts[start: right + 1]
    if not middle:
        desc, dept = "", ""
    elif len(middle) == 1:
        desc, dept = middle[0], ""  # single word treated as description
    else:
        dept = middle[-1]           # last word = Department
        desc = " ".join(middle[:-1])  # rest = Description

    # Strip stray PLU/pkg numbers that may have bled into description
    desc = re.sub(r"^\d{4,}\s*", "", desc).strip()
    desc = re.sub(r"^\d{1,2}\s+", "", desc).strip()

    # Reject rows where description/dept contain no letters
    # (e.g. clusters that are just a list of monetary values)
    if not re.search(r"[A-Za-z]", desc + dept):
        return None

    count = _parse_items_text(count_str) or 0
    price = _parse_money_text(price_str) or 0.0
    sales = _parse_money_text(sales_str) or 0.0
    if not sales and price and count:
        sales = round(price * count, 2)
    if not count and price and sales:
        count = max(1, round(sales / price))
    pct_d = _parse_decimal(pct_dept.replace("%", "").strip()) or 0.0
    pct_t = _parse_decimal(pct_total.replace("%", "").strip()) or 0.0

    return {
        "dept_num":    dept,
        "description": desc,
        "items":       count,        # Count
        "sales_gross": price,        # Price
        "refunds":     sales,        # Sales
        "discounts":   pct_d,        # % of Dept
        "net_sales":   pct_t,        # % of Total
    }


def _cluster_plu_row_columns(cluster: dict, positions: dict) -> dict:
    """Assign each word to the column whose header left-edge is the largest
    x-value that does not exceed the word's x-position (floor assignment).
    This correctly handles right-aligned numeric columns: a narrow digit like
    '1' may sit a few pixels to the RIGHT of the 'Count' header word start,
    but it still falls in the Count bucket instead of the Price bucket,
    because count_x <= '1'_x < price_x.
    """
    col_starts = sorted(
        [(positions[c], c) for c in _PLU_COL_ORDER if c in positions],
        key=lambda t: t[0],
    )
    cols = {c: [] for c in _PLU_COL_ORDER}
    for word in cluster["words"]:
        x = word["left"]
        assigned = col_starts[0][1] if col_starts else "desc"
        for col_x, col_name in col_starts:
            if col_x <= x:
                assigned = col_name
            else:
                break
        cols[assigned].append(word["text"])
    return {k: _normalize_field_text(" ".join(v)) for k, v in cols.items()}


def _is_plu_data_row(cols: dict) -> bool:
    """Return True if this cluster looks like a PLU Sales Report data row.
    Uses description + at least one numeric field as the signal.
    PLU No. is intentionally NOT checked: it is not needed in the output
    and OCR frequently mis-reads or mis-assigns it.
    """
    desc = cols.get("desc", "").strip()
    if not desc or len(desc) < 2:
        return False
    return bool(
        cols.get("count", "").strip()
        or cols.get("price", "").strip()
        or cols.get("sales", "").strip()
    )


def _parse_plu_report_overlay_words(overlay_words: list) -> tuple:
    """Parse PLU Sales Report from OCR.space overlay words.
    Each data row maps to one output dict with keys:
      dept_num, description, items, sales_gross, refunds, discounts, net_sales, price.
    """
    rows = []
    parse_errors = []
    # y_threshold=10: keeps all words in a single printed row together (OCR
    # y-variance < 5px) while keeping adjacent rows separate (~15-20px apart).
    clusters = _cluster_overlay_words(overlay_words, y_threshold=10)
    start_idx, positions = _find_plu_header_positions(clusters)

    import sys
    print(f"[PLU DEBUG] overlay_words={len(overlay_words)}, clusters={len(clusters)}, start_idx={start_idx}, positions={positions}", file=sys.stderr)

    if start_idx is None or len(positions) < 4:
        # Headerless continuation page: try format-based parsing without column positions.
        import sys as _sys
        print(f"[PLU HEADERLESS] Trying format-based parse on {len(clusters)} clusters", file=_sys.stderr)
        for _ci, _cluster in enumerate(clusters):
            _text_up = _cluster["text"].upper()
            if _ci < 5:  # Print first 5 cluster texts for diagnosis
                print(f"  [cluster {_ci}] {_cluster['text']!r}", file=_sys.stderr)
            if re.search(r"^TOTAL\s+PLU|GRAND\s+TOTAL|TAX\s+COLLECTION", _text_up):
                break
            # Only skip clusters where these words appear at the START (anchored)
            if re.search(r"^PAGE\s+\d|^PLU\s+NO|^DESCRIPTION\b|^DEPARTMENT\b|COUNT\s+PRICE", _text_up):
                continue
            _row = _parse_plu_row_by_format(_cluster)
            if _row:
                rows.append(_row)
        if rows:
            return rows, []
        diag = f"clusters={len(clusters)}, start_idx={start_idx}, positions={positions}"
        return rows, [f"No se pudo identificar la cabecera del PLU Sales Report ({diag})"]

    for cluster in clusters[start_idx + 1:]:
        text = _normalize_field_text(cluster["text"])
        if not text:
            continue
        text_up = text.upper()
        # Stop at grand-total / summary footers — nothing useful follows.
        if re.search(r"^TOTAL\s+PLU|GRAND\s+TOTAL|TAX\s+COLLECTION", text_up):
            break
        # Skip section headers, page markers, column-header repeats.
        if re.search(
            r"^PAGE\s+\d|^PLU\s+NO|DESCRIPTION|DEPARTMENT|COUNT\s+PRICE|STORE\s+CLOSE",
            text_up,
        ):
            continue

        cols = _cluster_plu_row_columns(cluster, positions)

        # If Count/Price/Sales contain only text (no digits) AND the text
        # is 4+ characters long, it is a department name word that overflowed
        # past the column boundary.  Short noise like "NEN" (OCR misread of
        # a digit) is left in place so the count fallback can handle it.
        for _spill in ("count", "price", "sales"):
            _v = cols.get(_spill, "")
            if _v and not re.search(r"\d", _v) and len(_v) >= 4:
                cols["dept"] = (cols.get("dept", "") + " " + _v).strip()
                cols[_spill] = ""

        if not _is_plu_data_row(cols):
            # May be a continuation line where the printer wrapped a long
            # department or description to the next print line.  Append to
            # the previous row only when: we already have at least one row,
            # and this cluster has text only in the dept/desc buckets (no
            # numeric columns filled).
            _cont_dept = cols.get("dept", "").strip()
            _cont_desc = cols.get("desc", "").strip()
            if rows and (_cont_dept or _cont_desc) and not any(
                cols.get(c, "").strip()
                for c in ("count", "price", "sales", "pct_dept", "pct_total")
            ):
                if _cont_dept:
                    rows[-1]["dept_num"] = (rows[-1].get("dept_num", "") + " " + _cont_dept).strip()
                if _cont_desc:
                    rows[-1]["description"] = (rows[-1].get("description", "") + " " + _cont_desc).strip()
            continue

        desc  = cols["desc"].strip()
        # Strip any leading PLU number (8-15 digits) or Pkg.Qty digit that
        # may have bled into the description column.
        desc = re.sub(r"^\d{6,15}\s*", "", desc).strip()
        desc = re.sub(r"^\d{1,2}\s+", "", desc).strip()
        dept  = cols["dept"].strip()
        count     = _parse_items_text(cols["count"]) or 0
        price     = _parse_money_text(cols["price"]) or 0.0
        sales     = _parse_money_text(cols["sales"]) or 0.0
        if not sales and price and count:
            sales = round(price * count, 2)
        # OCR frequently misses small isolated count digits (1, 2, 5…).
        # Derive count from sales÷price when both are available.
        if not count and price and sales:
            count = max(1, round(sales / price))
        pct_dept  = _parse_decimal(cols["pct_dept"].replace("%", "").strip()) or 0.0
        pct_total = _parse_decimal(cols["pct_total"].replace("%", "").strip()) or 0.0

        rows.append({
            "dept_num":    dept,
            "description": desc,
            "items":       count,       # Count
            "sales_gross": price,       # Price
            "refunds":     sales,       # Sales (count × price)
            "discounts":   pct_dept,    # % of Dept
            "net_sales":   pct_total,   # % of Total
        })

    return rows, parse_errors


def _parse_plu_report_lines(lines: list) -> tuple:
    """Fallback text parser for PLU Sales Report.
    OCR text mode may split each product across multiple lines, so we join
    consecutive lines that belong to the same row before parsing.
    """
    rows = []
    parse_errors = []
    in_report = False

    # Pre-filter: strip blanks, skip header/footer noise
    _SKIP_PAT = re.compile(
        r"PLU\s*NO|PKG\s*\.?\s*QTY|DESCRIPTION|COUNT\s+PRICE"
        r"|^PAGE\s+\d|GRAND\s+TOTAL|PLU\s+SALES\s+REPORT",
        re.IGNORECASE,
    )
    _PLU_START = re.compile(r"^\d{8,15}\b")
    _FULL_ROW  = re.compile(
        r"^(\d{8,15})"
        r"\s+(\d{1,2})"
        r"\s+(.+?)"
        r"\s+(\d{1,4})"
        r"\s+\$?([\d.,]+)"
        r"\s+\$?([\d.,]+)"
        r"\s+[\d.,]+%?"
        r"\s+[\d.,]+%?\s*$",
    )
    # Looser match when % columns are absent (just PLU qty desc count price sales)
    _LOOSE_ROW = re.compile(
        r"^(\d{8,15})"
        r"\s+(\d{1,2})"
        r"\s+(.+?)"
        r"\s+(\d{1,4})"
        r"\s+\$?([\d.,]+)"
        r"\s+\$?([\d.,]+)\s*$",
    )

    clean_lines = []
    for line in lines:
        line = line.strip()
        if re.search(r"PLU\s+SALES\s+REPORT", line, re.IGNORECASE):
            in_report = True
            continue
        # Headerless continuation page: auto-start when a PLU data row is seen
        if not in_report and _PLU_START.match(line):
            in_report = True
        if not in_report or not line:
            continue
        if _SKIP_PAT.search(line):
            continue
        clean_lines.append(line)

    # Join fragments: when a line is just a PLU number (possibly + pkg qty),
    # merge it with the following lines until the joined text matches a row.
    i = 0
    while i < len(clean_lines):
        line = clean_lines[i]

        # Try single-line full match first
        m = _FULL_ROW.match(line) or _LOOSE_ROW.match(line)
        if m:
            combined = m.group(3).strip()
            count    = int(m.group(4)) if m.group(4).isdigit() else 0
            price    = _parse_decimal(m.group(5))
            sales    = _parse_decimal(m.group(6))
            rows.append({
                "dept_num":    "",
                "description": combined,
                "items":       count,       # Count
                "sales_gross": price,       # Price
                "refunds":     sales,       # Sales (count × price)
                "discounts":   0.0,         # % of Dept (not in text mode)
                "net_sales":   0.0,         # % of Total (not in text mode)
            })
            i += 1
            continue

        # If the line starts with a PLU number, try joining the next few lines
        if _PLU_START.match(line):
            joined = line
            for j in range(i + 1, min(i + 5, len(clean_lines))):
                joined = joined + " " + clean_lines[j]
                m2 = _FULL_ROW.match(joined) or _LOOSE_ROW.match(joined)
                if m2:
                    combined = m2.group(3).strip()
                    count    = int(m2.group(4)) if m2.group(4).isdigit() else 0
                    price    = _parse_decimal(m2.group(5))
                    sales    = _parse_decimal(m2.group(6))
                    rows.append({
                        "dept_num":    "",
                        "description": combined,
                        "items":       count,       # Count
                        "sales_gross": price,       # Price
                        "refunds":     sales,       # Sales (count × price)
                        "discounts":   0.0,         # % of Dept (not in text mode)
                        "net_sales":   0.0,         # % of Total (not in text mode)
                    })
                    i = j + 1
                    break
            else:
                i += 1
            continue

        i += 1

    return rows, parse_errors


def parse_department_report_image(image_path: str) -> dict:
    """
    OCR una imagen de DEPARTMENT REPORT o PLU Sales Report y extrae filas de ventas.
    Detecta automáticamente el formato (DEPARTMENT REPORT o PLU Sales Report).
    Devuelve: {"rows": [...], "parse_errors": [...], "raw_text": str}
    Lanza RuntimeError si no hay OCR disponible.
    """
    try:
        from config import OCR_SPACE_API_KEY
        api_key = OCR_SPACE_API_KEY.strip()
    except Exception:
        api_key = ""

    raw_text = ""
    rows = []
    parse_errors = []
    report_type = "dept"

    if api_key:
        overlay_data = _ocr_with_ocrspace_overlay(image_path, api_key)
        raw_text = overlay_data["raw_text"]
        import sys
        is_plu_flag = _is_plu_sales_report(raw_text)
        print(f"[OCR DEBUG] raw_text[:300]={raw_text[:300]!r}", file=sys.stderr)
        print(f"[OCR DEBUG] is_plu={is_plu_flag}, overlay_words={len(overlay_data['overlay_words'])}", file=sys.stderr)
        if is_plu_flag:
            report_type = "plu"
            rows, parse_errors = _parse_plu_report_overlay_words(overlay_data["overlay_words"])
        else:
            rows, parse_errors = _parse_dept_report_overlay_words(overlay_data["overlay_words"])

    if not rows:
        raw_text = raw_text or _ocr_text(image_path)
        if _is_plu_sales_report(raw_text):
            report_type = "plu"
            text_rows, text_errors = _parse_plu_report_lines(raw_text.splitlines())
        else:
            text_rows, text_errors = _parse_dept_report_lines(raw_text.splitlines())
        if text_rows:
            rows = text_rows
        parse_errors.extend(text_errors)

    return {"rows": rows, "parse_errors": parse_errors, "raw_text": raw_text, "report_type": report_type}
