import sys
sys.path.insert(0, r"C:\Users\Ariel David\Desktop\MigasApp")
from utils.ocr_scan import _compute_desc_dept_boundary, _split_desc_dept_by_xgap

def w(text, left, top):
    return {"text": text, "left": left, "top": top}

def cluster(words_data):
    words = [w(t, l, y) for t, l, y in words_data]
    words.sort(key=lambda x: x["left"])
    return {"words": words, "text": " ".join(x["text"] for x in words), "top": words[0]["top"]}

# Photo 3 clusters (using real $ character)
ph3 = [
    cluster([("024474381014",640,476),("PETIT",1317,469),("TAX",1764,499),("GROCERY",1771,453),("NO",2000,453),("$",2448,484),("1.50",2448,484),("$",2679,491),("1.50",2679,491),("3.34",2895,499),("%",2895,499),("0.15",3118,499),("%",3118,499)]),
    cluster([("025000058011",625,580),("LEMONADE",1310,573),("20oz",1570,573),("GROCERY",1764,558),("TAX",1764,603),("NO",2003,558),("$",2455,587),("2.40",2455,587),("$",2687,595),("2.40",2687,595),("5.34",2902,595),("%",2902,595),("0.24",3126,603),("%",3126,603)]),
    cluster([("033544000267",618,685),("CHELADA",1310,677),("TAX",1756,714),("GROCERY",1764,662),("NO",2003,662),("$",2456,692),("4.00",2456,692),("$",2679,700),("4.00",2679,700),("8.90",2910,707),("%",2910,707),("0.40",3133,707),("%",3133,707)]),
    cluster([("040000001621",603,789),("SKITTLES",1302,788),("GROCERY",1764,773),("TAX",1764,819),("NO",1998,773),("$",2456,804),("1.85",2456,804),("$",2694,804),("3.70",2694,804),("8.23",2910,811),("%",2910,811),("0.37",3140,819),("%",3140,819)]),
    cluster([("049000003710",595,900),("PAWERADE",1295,900),("TAX",1756,930),("GROCERY",1764,878),("NO",1997,878),("$",2463,908),("1.87",2463,908),("$",2701,915),("1.87",2701,915),("4.16",2917,915),("%",2917,915),("0.19",3147,921),("%",3147,921)]),
]

bx3 = _compute_desc_dept_boundary(ph3)
print(f"Photo 3 boundary_x = {bx3}")
assert bx3 is not None, "Should not be None"
assert 1700 < bx3 < 1800, f"Expected ~1756-1764, got {bx3}"

# Photo 4 clusters
ph4 = [
    cluster([("076171101556",365,1518),("ICE",1139,1555),("LITTLE",1146,1496),("TREES",1324,1496),("BLK",1508,1496),("AUTO",1652,1525),("PARTS",1809,1525),("$",2441,1525),("1.50",2441,1525),("$",2709,1526),("1.50",2709,1526),("33.33",2925,1525),("%",2925,1525),("0.15",3207,1526),("%",3207,1526)]),
    cluster([("076171101891",357,1615),("NEW",1131,1621),("CAR",1270,1622),("AUTO",1660,1629),("PARTS",1803,1629),("$",2709,1630),("3.00",2709,1630),("66.67",2924,1622),("%",2924,1622),("0.30",3214,1628),("%",3214,1628)]),
    cluster([("810016102380",350,1682),("1",923,1689),("NEW",1139,1689),("CAR",1269,1689),("U",1393,1689),("FRESH",1438,1689),("AIR",1647,1689),("FRESHNER",1751,1689),("$",2679,1697),("10.32",2679,1697),("50.84",2917,1697),("%",2917,1697),("1.03",3222,1697),("%",3222,1697)]),
    cluster([("810016102502",342,1756),("HANING",1131,1764),("AIR",1652,1764),("FRESHNER",1742,1764),("$",2701,1763),("2.99",2701,1763),("14.73",2925,1764),("%",2925,1764),("0.30",3215,1764),("%",3215,1764)]),
    cluster([("810016102564",335,1823),("BLACK",1131,1830),("ICE",1313,1830),("AIR",1660,1838),("$",2716,1838),("6.99",2716,1838),("34.43",2932,1838),("%",2932,1838),("0.70",3230,1838),("%",3230,1838)]),
    cluster([("018200005428",335,1890),("BUSH",1131,1905),("SINGLE",1287,1905),("BEER",1652,1905),("SINGLE",1808,1905),("8",2292,1913),("$",2686,1903),("12.00",2686,1903),("14.58",2940,1913),("%",2940,1913),("1.20",3230,1913),("%",3230,1913)]),
]

bx4 = _compute_desc_dept_boundary(ph4)
print(f"Photo 4 boundary_x = {bx4}")
assert bx4 is not None, "Should not be None"
assert 1600 < bx4 < 1700, f"Expected ~1647-1660, got {bx4}"

# Test _split_desc_dept_by_xgap with computed boundaries
def make_tok(text, left, top):
    return ({"left": left, "top": top}, text)

# Photo 3 cluster 1: LEMONADE 20oz / GROCERY NO TAX
mid = [make_tok("LEMONADE",1310,573), make_tok("20oz",1570,573), make_tok("GROCERY",1764,558), make_tok("TAX",1764,603), make_tok("NO",2003,558)]
desc, dept = _split_desc_dept_by_xgap(mid, boundary_x=bx3)
print(f"Photo 3 cluster1: desc={desc!r} dept={dept!r}")
assert desc == "LEMONADE 20oz", f"Got {desc!r}"
assert dept == "GROCERY NO TAX", f"Got {dept!r}"

# Photo 4 cluster 0: LITTLE TREES BLK ICE / AUTO PARTS
mid4 = [make_tok("ICE",1139,1555), make_tok("LITTLE",1146,1496), make_tok("TREES",1324,1496), make_tok("BLK",1508,1496), make_tok("AUTO",1652,1525), make_tok("PARTS",1809,1525)]
desc4, dept4 = _split_desc_dept_by_xgap(mid4, boundary_x=bx4)
print(f"Photo 4 cluster0: desc={desc4!r} dept={dept4!r}")
assert desc4 == "LITTLE TREES BLK ICE", f"Got {desc4!r}"
assert dept4 == "AUTO PARTS", f"Got {dept4!r}"

# Bare-integer ambiguity: BUSH SINGLE count=8 price=1.50 sales=12.0
from utils.ocr_scan import _parse_money_text, _parse_items_text, _parse_decimal
price = _parse_money_text("8") or 0.0
count = _parse_items_text("") or 0
sales = _parse_money_text("$12.00") or 0.0
price_str = "8"
if price > 0 and count == 0 and sales > 0 and "." not in price_str.replace("$", ""):
    derived_count_a = round(sales / price)
    if derived_count_a > 0 and abs(derived_count_a * price - sales) > 0.02:
        candidate_count = int(price)
        if candidate_count > 0:
            derived_price = sales / candidate_count
            if abs(derived_price - round(derived_price, 2)) < 0.001:
                count = candidate_count
                price = round(derived_price, 2)
print(f"BUSH SINGLE: count={count} price={price}")
assert count == 8 and abs(price - 1.5) < 0.01, f"Got count={count} price={price}"

print("\nAll tests PASSED!")
