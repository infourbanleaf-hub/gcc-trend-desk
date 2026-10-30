"""Build products.json for the GCC Product Wall from dashboard/data.json + img/.

Usage: python dashboard/build_wall.py <repo dir> <out.json> [YYYY-MM-DD]
"""
import base64, json, sys
from pathlib import Path

repo = Path(sys.argv[1])
out = Path(sys.argv[2])
items = json.loads((repo / "dashboard/data.json").read_text(encoding="utf-8"))
from datetime import datetime, timedelta

def pdate(v):
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(v).strip()[:19], f)
        except ValueError:
            pass
    return None

today = datetime(*map(int, sys.argv[3].split("-"))) if len(sys.argv) > 3 else datetime.now()
week_ago = today - timedelta(days=7)
# Amazon and Meta rows repeat across weekly scans: keep the latest row per link, remember the first sighting.
first, latest = {}, {}
for it in items:
    if it["type"] in ("Amazon", "Meta ad") and it.get("url"):
        k = (it["type"], it["url"])
        d = pdate(it.get("date")) or datetime(2000, 1, 1)
        first[k] = min(first.get(k, d), d)
        if k not in latest or d >= (pdate(latest[k].get("date")) or datetime(2000, 1, 1)):
            latest[k] = it
keep = []
for it in items:
    k = (it["type"], it.get("url"))
    if it["type"] in ("Amazon", "Meta ad") and it.get("url"):
        if latest.get(k) is not it:
            continue
        it["first_seen"] = first[k]
    keep.append(it)
items = keep

# YouTube search returns many off-topic videos (phone launches, money-making, family vlogs).
# Keep only titles about buyable products, and one card per title.
import re
YT_KEEP = re.compile(r"amazon|\bfinds?\b|gadget|products?\b|productos|kitchen|tools?\b|must.?have|useful|organi[sz]|accessor|temu|shein|meesho|"
                     r"dicer|chopper|cutter|home ?essentials|homedecor|"
                     r"منتج|أدا[ةو]|ادوات|أدوات|مطبخ|امازون|أمازون|شي ?ان|تيمو|اكسسوار|مفيد", re.I)
YT_DROP = re.compile(r"iphone|xiaomi|samsung|vivo|realme|ps5|playstation|money|\bai\b|inteligencia|tesla|challenge|prank|squishy|needoh|"
                     r"sephora|snack|groceries|ranking|cheating|collagen|instagram ads|celebrity|wedding|maternity|trimester|costume|"
                     r"dreamina|cycling|smart tv|bottles|employee|mom can|stop talking|fire in toilet|who won|sister|dumpling|gastando|farmacia|crazy|ضحك|اكسبلور|نانا|شهاب|غزل|ندوشة|جوان|ليليان|هيلين|دانيال|خلودة|غفران|حمامات|البابا", re.I)
seen_titles, kept = set(), []
for it in items:
    if it["type"] == "YouTube":
        t = str(it.get("title", ""))
        key = re.sub(r"\W+", "", t.lower())[:60]
        if not YT_KEEP.search(t) or YT_DROP.search(t) or key in seen_titles:
            continue
        seen_titles.add(key)
    kept.append(it)
items = kept
rows = []
for it in items:
    img = ""
    if it.get("img"):
        f = repo / "dashboard/img" / it["img"]
        if f.exists():
            img = "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
    cs = [c for c in it.get("countries", []) if c]
    if it["type"] == "YouTube":
        fs = pdate(it.get("published"))
    elif it["type"] == "Candidate":
        fs = pdate(it.get("date"))
    else:
        fs = it.get("first_seen")
    is_new = bool(fs and fs >= week_ago)
    rows.append({"new": is_new, "first_seen": fs.strftime("%Y-%m-%d") if fs else "",
        "id": it["id"], "type": it["type"], "title": str(it.get("title", "")).strip(),
        "url": it.get("url", ""), "country": ", ".join(cs) or "GCC",
        "source": str(it.get("source", "")), "price": it.get("price"),
        "price_label": it.get("price_label", "") or "",
        "views": it.get("views"), "likes": it.get("likes"), "days": it.get("days"),
        "reviews": it.get("reviews"), "rank": it.get("rank"), "movement": it.get("movement", "") or "",
        "signals": it.get("signals"), "status": it.get("status", "") or "",
        "note": str(it.get("note", "") or "")[:200], "date": it.get("date", ""), "img": img,
    })
out.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(sum(r["new"] for r in rows), "new;", len(rows), "rows,", round(out.stat().st_size / 1e6, 2), "MB,", sum(1 for r in rows if r["img"]), "with pictures")
