import sys
sys.path.insert(0, r"C:\Users\Ariel David\Desktop\MigasApp")
from utils.ocr_scan import parse_department_report_image

for img in ["3.jpeg", "4.jpeg"]:
    result = parse_department_report_image(rf"C:\Users\Ariel David\Desktop\MigasApp\{img}")
    print(f"\n=== {img} | type={result['report_type']} | rows={len(result['rows'])} ===")
    for r in result["rows"]:
        print(f"  {r['description']!r:30s} dept={r['dept_num']!r:20s} cnt={r['items']:3d} price={r['sales_gross']:7.2f} sales={r['refunds']:8.2f}")
    if result["parse_errors"]:
        print(f"  ERRORS: {result['parse_errors']}")
