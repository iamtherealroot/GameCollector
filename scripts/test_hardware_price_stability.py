"""Exercise the real valuation functions with offline marketplace fixtures."""
import ast
import json
import math
import re
import statistics
import unicodedata
from pathlib import Path
from types import SimpleNamespace as NS

source = Path(__file__).resolve().parents[1] / "app/app.py"
tree = ast.parse(source.read_text())
names = {"_match_key", "hardware_auto_value"}
nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and
         (node.name in names or node.name.startswith("_hardware_"))]
scope = dict(re=re, math=math, statistics=statistics, unicodedata=unicodedata, json=json)
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), scope)
item = NS(model=NS(name="Microsoft Xbox Series X", model_number="", color="", edition="", pricecharting_url=""),
          condition=8, set_condition=8, completeness="Konsole + Zubehör", tested_status="tested",
          id=1, auto_value_eur=50, auto_value_updated_at="old")


def row(title, price, n, **extra):
    return dict(name=title, price=price, currency="EUR", id=str(n), url=f"https://www.ebay.de/itm/{n}",
                details_checked=True, **extra)


scope["ebay_enrich_candidates"] = lambda rows, **_: rows
bad = [
    row("Microsoft Xbox Series S Konsole", 50, 1),
    row("Xbox One X Konsole", 50, 2),
    row("Controller für Xbox Series X Konsole", 50, 3),
    row("Xbox Series X OVP only", 50, 4),
    row("Xbox Series X Konsole", 50, 5, condition_id="7000"),
    row("Xbox Series X Konsole", 50, 6, category="Zubehör"),
    row("Xbox Series X Konsole", 50, 7, buying_options=["AUCTION"]),
    row("Xbox Series X Konsole, Anzahlung", 50, 8),
    row("Xbox Series X Konsole", 50, 9),
]
good = [row("Xbox Series X Konsole mit Controller", price, n)
        for n, price in enumerate([330, 340, 350, 360, 370], 10)]
scope["_hardware_ebay_search_with_retry"] = lambda *a, **kw: (bad + good + good, "ok")
estimate = scope["_hardware_ebay_value"]
result, status = estimate(item, reference_value=350)
assert status == "ok" and result["count"] == 5
assert result["sample_urls"] == [r["url"] for r in good]
assert 300 < result["value"] < 400
assert estimate(item)[1] == "hardware_reference_missing"
scope["_hardware_ebay_search_with_retry"] = lambda *a, **kw: (bad + good[:1] * 5, "ok")
assert estimate(item, reference_value=350)[1] == "too_few_results"

# A bad scan must not refresh an old value's timestamp or add price history.
scope["calculate_hardware_set"] = lambda item: None
scope["utc_now"] = lambda: "new"
scope["pricecharting_hardware_value"] = lambda item: (None, "pricecharting_wrong_product")
assert scope["hardware_auto_value"](item) == (False, "hardware_reference_missing")
assert item.auto_value_eur == 50 and item.auto_value_updated_at == "old"
assert "nicht bestätigt" in item.auto_value_message
print("OK: hardware identity, accessories, price anchor, distinct samples and failed-scan preservation")
