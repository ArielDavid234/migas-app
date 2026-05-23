import sys, traceback
sys.path.insert(0, r"C:\Users\Ariel David\Desktop\MigasApp")
from utils.ocr_scan import (
    _ocrspace_request, _auto_y_threshold, _cluster_overlay_words,
    _find_plu_header_positions, _cluster_plu_by_barcode_anchors,
    _compute_desc_dept_boundary, _parse_plu_row_by_format, _normalize_word_text,
    _cluster_plu_row_columns, _is_plu_data_row,
)

def test_photo(path, label):
    print(f"\n{'='*60}\nPHOTO: {label}\n{'='*60}")
    try:
        data = _ocrspace_request(path, "K84112862188957", language="eng", overlay=True)
    except Exception as e:
        print(f"OCR request failed: {e}")
        return
    result = data["ParsedResults"][0]
    overlay = result.get("TextOverlay", {})
    lines_raw = overlay.get("Lines", [])
    all_words = []
    for line in lines_raw:
        for w in line.get("Words", []):
            all_words.append({"text": w["WordText"], "left": w["Left"], "top": w["Top"]})

    print(f"total words={len(all_words)}")
    y_thresh = _auto_y_threshold(all_words)
    thresh_clusters = _cluster_overlay_words(all_words, y_threshold=y_thresh)
    start_idx, positions = _find_plu_header_positions(thresh_clusters)
    print(f"Header: start_idx={start_idx}, positions={positions}")

    if start_idx is not None and len(positions) >= 4:
        print("\n[COLUMN-BASED PARSER]")
        for i, cluster in enumerate(thresh_clusters[start_idx+1:]):
            cols = _cluster_plu_row_columns(cluster, positions)
            if _is_plu_data_row(cols):
                desc = cols.get("desc", "")
                dept = cols.get("dept", "")
                count = cols.get("count", "")
                price = cols.get("price", "")
                sales = cols.get("sales", "")
                pct_d = cols.get("pct_dept", "")
                pct_t = cols.get("pct_total", "")
                print(f"  Row {i}: desc={desc!r} dept={dept!r} count={count!r} price={price!r} sales={sales!r}")
    else:
        anchor_clusters = _cluster_plu_by_barcode_anchors(all_words)
        bx = _compute_desc_dept_boundary(anchor_clusters)
        print(f"\n[BARCODE-ANCHOR]: {len(anchor_clusters)} clusters, boundary_x={bx}")
        for i, cluster in enumerate(anchor_clusters):
            words_sorted = sorted(
                [w for w in cluster["words"] if _normalize_word_text(w["text"])],
                key=lambda w: w["left"]
            )
            tokens = [(w["left"], w["text"]) for w in words_sorted]
            row = _parse_plu_row_by_format(cluster, boundary_x=bx)
            if row:
                print(f"  [{i:2d}] desc={row['description']!r} dept={row['dept_num']!r} "
                      f"count={row['items']} price={row['sales_gross']} sales={row['refunds']} "
                      f"pct_d={row['discounts']} pct_t={row['net_sales']}")
                print(f"        tokens={tokens}")
            else:
                print(f"  [{i:2d}] SKIP  tokens={tokens}")

test_photo(r"C:\Users\Ariel David\Desktop\MigasApp\2.jpeg", "2.jpeg")
test_photo(r"C:\Users\Ariel David\Desktop\MigasApp\3.jpeg", "3.jpeg")
test_photo(r"C:\Users\Ariel David\Desktop\MigasApp\4.jpeg", "4.jpeg")
