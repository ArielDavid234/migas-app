import sys
sys.path.insert(0, r"C:\Users\Ariel David\Desktop\MigasApp")
from utils.ocr_scan import _ocr_with_ocrspace_overlay, _cluster_overlay_words, _find_plu_header_positions
from config import OCR_SPACE_API_KEY
data = _ocr_with_ocrspace_overlay(r"C:\Users\Ariel David\Desktop\MigasApp\3.jpeg", OCR_SPACE_API_KEY.strip())
print("RAW TEXT (first 500 chars)")
print(data["raw_text"][:500])
clusters = _cluster_overlay_words(data["overlay_words"], y_threshold=10)
print("\nFIRST 5 CLUSTERS")
for cl in clusters[:5]:
    print(f"  top={cl['top']:4d}  {cl['text']!r}")
si, pos = _find_plu_header_positions(clusters)
print(f"header start_idx={si}, positions={pos}")
