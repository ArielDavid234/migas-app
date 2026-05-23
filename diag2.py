import sys, re
sys.path.insert(0, r"C:\Users\Ariel David\Desktop\MigasApp")
from utils.ocr_scan import (
    _ocrspace_request, _cluster_overlay_words, _auto_y_threshold,
    _cluster_plu_by_barcode_anchors, _parse_plu_row_by_format,
    _compute_desc_dept_boundary,
    _find_plu_header_positions, _cluster_plu_row_columns, _is_plu_data_row,
    _normalize_word_text,
)

def test_photo(path, label):
    print(f"\n{'='*60}\nPHOTO: {label}\n{'='*60}")
    data = _ocrspace_request(path, "K84112862188957", language="eng", overlay=True)
    result = data["ParsedResults"][0]
    overlay = result.get("TextOverlay", {})
    lines_raw = overlay.get("Lines", [])
    all_words = []
    for line in lines_raw:
        for w in line.get("Words", []):
            all_words.append({"text": w["WordText"], "left": w["Left"], "top": w["Top"]})

    y_thresh = _auto_y_threshold(all_words)
    print(f"y_thresh={y_thresh}, total words={len(all_words)}")

    # Try column-based (header page path)
    thresh_clusters = _cluster_overlay_words(all_words, y_threshold=y_thresh)
    start_idx, positions = _find_plu_header_positions(thresh_clusters)
    print(f"Header found: start_idx={start_idx}, positions={positions}")

    if start_idx is not None and len(positions) >= 4:
        print("\n[COLUMN-BASED PARSER]")
        rows_found = 0
        for i, cluster in enumerate(thresh_clusters[start_idx+1:start_idx+15]):
            cols = _cluster_plu_row_columns(cluster, positions)
            if _is_plu_data_row(cols):
                print(f"  Row {i}: desc={cols.get('desc','')!r}  dept={cols.get('dept','')!r}  "
                      f"count={cols.get('count','')!r}  price={cols.get('price','')!r}  "
                      f"sales={cols.get('sales','')!r}  pct_dept={cols.get('pct_dept','')!r}  "
                      f"pct_total={cols.get('pct_total','')!r}")
                rows_found += 1
        print(f"  ... (showing first 14 data rows, found {rows_found})")
    else:
        # Barcode-anchor path
        anchor_clusters = _cluster_plu_by_barcode_anchors(all_words)
        boundary_x = _compute_desc_dept_boundary(anchor_clusters)
        print(f"\n[BARCODE-ANCHOR CLUSTERS]: {len(anchor_clusters)} clusters  boundary_x={boundary_x}")
        rows_found = 0
        for i, cluster in enumerate(anchor_clusters[:6]):
            # Show raw x-sorted tokens for diagnosis
            words = [w for w in cluster["words"] if _normalize_word_text(w["text"])]
            sorted_w = sorted(words, key=lambda w: w["left"])
            print(f"\n  --- Cluster {i} raw tokens (x-sorted) ---")
            for w in sorted_w:
                print(f"    x={w['left']:5d} y={w['top']:5d}  {w['text']!r}")
            row = _parse_plu_row_by_format(cluster, boundary_x=boundary_x)
            if row:
                print(f"  => desc={row['description']!r}  dept={row['dept_num']!r}  "
                      f"count={row['items']}  price={row['sales_gross']}  "
                      f"sales={row['refunds']}  pct_d={row['discounts']}  pct_t={row['net_sales']}")
                rows_found += 1
            else:
                print(f"  => SKIP: {cluster['text'][:60]!r}")
        print(f"\n  ... (showing detail for first 6 clusters)")

test_photo(r"C:\Users\Ariel David\Desktop\MigasApp\3.jpeg", "3.jpeg")
test_photo(r"C:\Users\Ariel David\Desktop\MigasApp\4.jpeg", "4.jpeg")
