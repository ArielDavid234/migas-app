import sys
sys.path.insert(0, r"C:\Users\Ariel David\Desktop\MigasApp")
from utils.ocr_scan import _ocrspace_request, _cluster_overlay_words, _find_plu_header_positions, _PLU_COL_ORDER, _cluster_plu_row_columns, _normalize_field_text

data = _ocrspace_request(
    r"C:\Users\Ariel David\Desktop\MigasApp\2.jpeg",
    "K84112862188957",
    language="eng",
    overlay=True
)

result = data["ParsedResults"][0]
overlay = result.get("TextOverlay", {})
lines = overlay.get("Lines", [])

words = []
for line in lines:
    for w in line.get("Words", []):
        words.append({"text": w["WordText"], "left": w["Left"], "top": w["Top"]})

print(f"Total words: {len(words)}")
print()

# Show first 60 words with coords
for i, w in enumerate(words[:60]):
    print(f"  [{i:3d}] x={w['left']:4d} y={w['top']:4d}  {w['text']!r}")

print()
# Find header cluster
clusters = _cluster_overlay_words(words, y_threshold=10)
print(f"Total clusters: {len(clusters)}")
start_idx, positions = _find_plu_header_positions(clusters)
print(f"Header at cluster {start_idx}, positions={positions}")
print()

# Show first 8 data clusters
for i, cluster in enumerate(clusters[start_idx+1:start_idx+10] if start_idx is not None else clusters[:10]):
    print(f"Cluster {start_idx+1+i if start_idx is not None else i}: y={cluster['top']}  text={cluster['text']!r}")
    cols = _cluster_plu_row_columns(cluster, positions)
    for k,v in cols.items():
        if v:
            print(f"    {k}: {v!r}")
    print()
