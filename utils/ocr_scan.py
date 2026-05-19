"""OCR scanning — uses OCR.space API (iOS/macOS/Windows)
   Falls back to local Tesseract if no API key configured (desktop only)."""

import base64
import re
from database.db import get_session
from database.models import Product, ProductStatus


def _ocrspace_request(image_path: str, api_key: str, *, language: str = "spa", overlay: bool = False) -> dict:
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
        "language": language,
        "isOverlayRequired": overlay,
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
    """Detect PLU Sales Report format (vs. old DEPARTMENT REPORT)."""
    t = raw_text.upper()
    return "PLU SALES REPORT" in t or (
        "PLU" in t and "COUNT" in t and "PRICE" in t
        and ("DESCRIPTION" in t or "DEPT" in t)
    )


def _find_plu_header_positions(clusters: list) -> tuple:
    """Find column x-positions from the PLU Sales Report header.
    Returns (start_idx, positions_dict) with keys:
      plu, pkg, desc, dept, count, price, sales, pct_dept, pct_total.
    """
    start_idx = None
    positions = {}

    for index, cluster in enumerate(clusters):
        text_up = cluster["text"].upper()

        if start_idx is None:
            if "PLU" in text_up and (
                "SALES" in text_up or "REPORT" in text_up or "NO" in text_up
            ):
                start_idx = index
                continue

        if start_idx is None:
            continue

        for word in cluster["words"]:
            word_up = word["text"].upper().strip(".,;:!")
            left = word["left"]
            if word_up == "PLU" and "plu" not in positions:
                positions["plu"] = left
            elif word_up in {"PKG", "PKG."} and "pkg" not in positions:
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
                elif "pct_total" not in positions and left != positions.get("pct_dept"):
                    positions["pct_total"] = left

        if len(positions) >= 5:
            break

    return start_idx, positions


def _build_plu_column_bounds(positions: dict) -> dict:
    """Compute midpoint x-boundaries between PLU Sales Report columns."""
    plu_x       = positions.get("plu",       0)
    pkg_x       = positions.get("pkg",       plu_x + 90)
    desc_x      = positions.get("desc",      pkg_x + 55)
    dept_x      = positions.get("dept",      desc_x + 95)
    count_x     = positions.get("count",     dept_x + 75)
    price_x     = positions.get("price",     count_x + 40)
    sales_x     = positions.get("sales",     price_x + 50)
    pct_dept_x  = positions.get("pct_dept",  sales_x + 55)
    pct_total_x = positions.get("pct_total", pct_dept_x + 55)

    def _mid(a, b):
        return int((a + b) / 2)

    return {
        "plu_pkg":        _mid(plu_x,      pkg_x),
        "pkg_desc":       _mid(pkg_x,      desc_x),
        "desc_dept":      _mid(desc_x,     dept_x),
        "dept_count":     _mid(dept_x,     count_x),
        "count_price":    _mid(count_x,    price_x),
        "price_sales":    _mid(price_x,    sales_x),
        "sales_pct":      _mid(sales_x,    pct_dept_x),
        "pct_dept_total": _mid(pct_dept_x, pct_total_x),
    }


def _cluster_plu_row_columns(cluster: dict, bounds: dict) -> dict:
    """Bucket words in a PLU row cluster into named column slots."""
    cols = {
        "plu": [], "pkg": [], "desc": [], "dept": [],
        "count": [], "price": [], "sales": [], "pct_dept": [], "pct_total": [],
    }
    for word in cluster["words"]:
        x = word["left"]
        if x < bounds["plu_pkg"]:
            cols["plu"].append(word["text"])
        elif x < bounds["pkg_desc"]:
            cols["pkg"].append(word["text"])
        elif x < bounds["desc_dept"]:
            cols["desc"].append(word["text"])
        elif x < bounds["dept_count"]:
            cols["dept"].append(word["text"])
        elif x < bounds["count_price"]:
            cols["count"].append(word["text"])
        elif x < bounds["price_sales"]:
            cols["price"].append(word["text"])
        elif x < bounds["sales_pct"]:
            cols["sales"].append(word["text"])
        elif x < bounds["pct_dept_total"]:
            cols["pct_dept"].append(word["text"])
        else:
            cols["pct_total"].append(word["text"])
    return {
        key: _normalize_field_text(" ".join(vals))
        for key, vals in cols.items()
    }


def _is_plu_data_row(cols: dict) -> bool:
    """Return True if this cluster looks like a PLU Sales Report data row."""
    plu_text = cols.get("plu", "").replace(" ", "")
    return (
        bool(re.match(r"^\d{8,15}$", plu_text))
        and bool(cols.get("desc", "").strip())
    )


def _parse_plu_report_overlay_words(overlay_words: list) -> tuple:
    """Parse PLU Sales Report from OCR.space overlay words.
    Each data row maps to one output dict with keys:
      dept_num, description, items, sales_gross, refunds, discounts, net_sales, price.
    """
    rows = []
    parse_errors = []
    clusters = _cluster_overlay_words(overlay_words)
    start_idx, positions = _find_plu_header_positions(clusters)

    if start_idx is None or len(positions) < 4:
        return rows, ["No se pudo identificar la cabecera del PLU Sales Report"]

    bounds = _build_plu_column_bounds(positions)

    for cluster in clusters[start_idx + 1:]:
        text = _normalize_field_text(cluster["text"])
        if not text:
            continue
        text_up = text.upper()
        # Skip header / footer / page marker rows
        if re.search(
            r"^PAGE\s+\d|GRAND\s+TOTAL|^PLU\s+NO|DESCRIPTION|DEPARTMENT|COUNT\s+PRICE",
            text_up,
        ):
            continue

        cols = _cluster_plu_row_columns(cluster, bounds)
        if not _is_plu_data_row(cols):
            continue

        desc  = cols["desc"].strip()
        dept  = cols["dept"].strip()
        count = _parse_items_text(cols["count"]) or 0
        price = _parse_money_text(cols["price"]) or 0.0
        sales = _parse_money_text(cols["sales"]) or 0.0
        if not sales and price and count:
            sales = round(price * count, 2)

        rows.append({
            "dept_num":    dept,
            "description": desc,
            "items":       count,
            "sales_gross": sales,
            "refunds":     0.0,
            "discounts":   0.0,
            "net_sales":   sales,
            "price":       price,
        })

    return rows, parse_errors


def _parse_plu_report_lines(lines: list) -> tuple:
    """Fallback text parser for PLU Sales Report.
    Each row: PLU_NO  PKG_QTY  DESCRIPTION [DEPARTMENT]  COUNT  PRICE  SALES  %DEPT  %TOTAL
    In text mode, Description and Department are merged into one description field.
    """
    rows = []
    parse_errors = []
    in_report = False

    for line in lines:
        line = line.strip()
        if re.search(r"PLU\s+SALES\s+REPORT", line, re.IGNORECASE):
            in_report = True
            continue
        if not in_report or not line:
            continue
        # Skip header / page marker lines
        if re.search(
            r"PLU\s*NO|PKG\s*\.?\s*QTY|DESCRIPTION|COUNT\s+PRICE|^PAGE\s+\d|GRAND\s+TOTAL",
            line, re.IGNORECASE,
        ):
            continue

        m = re.match(
            r"^(\d{8,15})"          # PLU No.
            r"\s+(\d{1,2})"         # Pkg. Qty
            r"\s+(.+?)"             # Description + Department (merged in text mode)
            r"\s+(\d{1,4})"         # Count
            r"\s+\$?([\d.,]+)"      # Price
            r"\s+\$?([\d.,]+)"      # Sales
            r"\s+([\d.,]+)%?"       # % of Dept
            r"\s+([\d.,]+)%?\s*$",  # % of Total
            line,
        )
        if m:
            combined = m.group(3).strip()
            count    = int(m.group(4)) if m.group(4).isdigit() else 0
            price    = _parse_decimal(m.group(5))
            sales    = _parse_decimal(m.group(6))
            rows.append({
                "dept_num":    "",
                "description": combined,
                "items":       count,
                "sales_gross": sales,
                "refunds":     0.0,
                "discounts":   0.0,
                "net_sales":   sales,
                "price":       price,
            })

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

    if api_key:
        overlay_data = _ocr_with_ocrspace_overlay(image_path, api_key)
        raw_text = overlay_data["raw_text"]
        if _is_plu_sales_report(raw_text):
            rows, parse_errors = _parse_plu_report_overlay_words(overlay_data["overlay_words"])
        else:
            rows, parse_errors = _parse_dept_report_overlay_words(overlay_data["overlay_words"])

    if not rows:
        raw_text = raw_text or _ocr_text(image_path)
        if _is_plu_sales_report(raw_text):
            text_rows, text_errors = _parse_plu_report_lines(raw_text.splitlines())
        else:
            text_rows, text_errors = _parse_dept_report_lines(raw_text.splitlines())
        if text_rows:
            rows = text_rows
        parse_errors.extend(text_errors)

    return {"rows": rows, "parse_errors": parse_errors, "raw_text": raw_text}
