import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.ocr_scan import (
    _ocr_with_ocrspace_overlay, _cluster_plu_by_barcode_anchors,
    _parse_plu_row_by_format, _compute_desc_dept_boundary
)
from config import OCR_SPACE_API_KEY

data = _ocr_with_ocrspace_overlay('3.jpeg', OCR_SPACE_API_KEY.strip())
words = data['overlay_words']
clusters = _cluster_plu_by_barcode_anchors(words)
boundary = _compute_desc_dept_boundary(clusters)
print(f'boundary_x={boundary}  total_clusters={len(clusters)}')
print()
for i, cl in enumerate(clusters):
    tokens = [(w["left"], w["top"], w["text"]) for w in cl["words"]]
    row = _parse_plu_row_by_format(cl, boundary_x=boundary)
    desc  = row["description"] if row else "[NONE]"
    dept  = row["dept_num"]    if row else ""
    price = row["sales_gross"] if row else 0
    sales = row["refunds"]     if row else 0
    count = row["items"]       if row else 0
    print(f'--- Cluster {i:02d} top={cl["top"]:4d} ---')
    for x, y, t in tokens:
        print(f'   x={x:4d} y={y:4d}  "{t}"')
    print(f'   => DESC="{desc}"  DEPT="{dept}"  cnt={count}  price={price}  sales={sales}')
    print()
