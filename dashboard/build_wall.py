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
# The same product often shows up on several platforms (a candidate that is also a Meta ad, an Amazon item
# in both UAE and KSA). Merge those into one card: countries combined, earliest sighting kept, and the
# other platforms counted as extra proof.
ORDER = {"Candidate": 0, "Amazon": 1, "Meta ad": 2, "Video product": 3}
by_key, merged = {}, []
for it in items:
    if it["type"] == "YouTube":
        merged.append(it)
        continue
    key = re.sub(r"\W+", "", str(it.get("title", "")).lower())[:40]
    if not key:
        merged.append(it)
        continue
    by_key.setdefault(key, []).append(it)
for key, group in by_key.items():
    group.sort(key=lambda x: ORDER.get(x["type"], 9))
    main = group[0]
    main["also"] = []
    for o in group[1:]:
        for c in o.get("countries", []):
            if c and c not in main.setdefault("countries", []):
                main["countries"].append(c)
        if main.get("price") in (None, "") and o.get("price") not in (None, ""):
            main["price"], main["price_label"] = o["price"], o.get("price_label", "")
        if not main.get("img") and o.get("img"):
            main["img"], main["ref"] = o["img"], o.get("ref")
        f_main = main.get("first_seen") or pdate(main.get("date"))
        f_o = o.get("first_seen") or pdate(o.get("date"))
        if f_o and (not f_main or f_o < f_main):
            main["first_seen"] = f_o
        main["also"].append({"type": o["type"], "url": o.get("url", ""), "source": str(o.get("source", ""))})
    merged.append(main)
print(len(items) - len(merged), "duplicate cards merged")
items = merged

# Market-insight fields: Google Product Taxonomy, lifecycle stage, opportunity score (see insights.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import insights
SRC = {"Amazon": "Marketplace", "Meta ad": "Meta ads", "YouTube": "YouTube", "Video product": "YouTube", "Candidate": "Candidates"}
for it in items:
    text = " ".join(str(it.get(k, "")) for k in ("title", "keyword"))
    top, path, gid = insights.google_category(text)
    if not path and it["type"] == "YouTube":
        top, path, gid = "Mixed product videos", "", ""
    it["gtop"], it["gpath"], it["gid"] = top, path, gid
    parts = path.split(" > ") if path else [top]
    it["gcat"] = " > ".join(parts[:2]) if len(parts) > 1 else parts[0]
    it["gkey"] = " > ".join(parts[:3])
    it["stage"] = insights.lifecycle(it, today, pdate)
TRADE = {}
_tf = repo / "dashboard" / "trade.json"
if _tf.exists():
    for t in json.loads(_tf.read_text(encoding="utf-8")):
        if t.get("change") not in ("", None):
            TRADE[(str(t["hs"]), t["country"])] = float(t["change"])
for it in items:
    it["hs"] = insights.hs_code(" ".join(str(it.get(k, "")) for k in ("title", "keyword")))
    cs = [c for c in it.get("countries", []) if c in ("UAE", "Saudi Arabia", "Kuwait", "Qatar", "Oman")] or ["UAE", "Saudi Arabia", "Kuwait", "Qatar", "Oman"]
    vals = [TRADE[(it["hs"], c)] for c in cs if (it["hs"], c) in TRADE]
    it["trade_change"] = max(vals) if vals else None
groups = {}
for it in items:
    for c in ([c for c in it.get("countries", []) if c] or ["GCC"]):
        groups.setdefault((it["gkey"], c), set()).add(SRC.get(it["type"], it["type"]))
for it in items:
    cs = [c for c in it.get("countries", []) if c] or ["GCC"]
    srcs = set().union(*[groups.get((it["gkey"], c), set()) for c in cs], groups.get((it["gkey"], "GCC"), set()))
    if it["gkey"] in ("Mixed product videos", "Other"):
        srcs = {SRC.get(it["type"], it["type"])}
    srcs = set(srcs) | {SRC.get(a["type"], a["type"]) for a in it.get("also", [])}
    it["proof_sources"] = sorted(srcs)
    if it["type"] == "YouTube":  # a video, not one product: no score (its products are scored when named)
        it["score"], it["score_parts"] = None, {}
    else:
        it["score"], it["score_parts"] = insights.score(it, len(srcs), it["trade_change"])

rows = []
for it in items:
    img = ""
    if it.get("img"):
        f = repo / "dashboard/img" / it["img"]
        if f.exists():
            import io
            from PIL import Image  # shrink to card size so the wall loads fast (about 2 MB in all)
            im = Image.open(f).convert("RGB")
            im.thumbnail((260, 260))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=62, optimize=True)
            img = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    cs = [c for c in it.get("countries", []) if c]
    if it["type"] == "YouTube":
        fs = pdate(it.get("published"))
    elif it["type"] == "Video product":
        fs = pdate(it.get("date"))
    elif it["type"] == "Candidate":
        fs = it.get("first_seen") or pdate(it.get("date"))
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
        "video": it.get("video", "") or "",
        "ref": bool(it.get("ref")), "ref_url": it.get("ref_url", "") or "",
        "category": it["gcat"], "gpath": it["gpath"], "gid": it["gid"],
        "stage": it["stage"], "score": it["score"],
        "sp_demand": it["score_parts"].get("demand"), "sp_proof": it["score_parts"].get("proof"),
        "sp_momentum": it["score_parts"].get("momentum"), "sp_price": it["score_parts"].get("price"),
        "sp_fit": it["score_parts"].get("fit"), "sp_trade": it["score_parts"].get("trade"),
        "hs": it["hs"], "trade_change": it["trade_change"],
        "proof_sources": ", ".join(it["proof_sources"]),
        "margin": it.get("margin"), "india_cost": it.get("india_cost"),
        "evidence": insights.evidence(it)[1] if it["type"] == "Candidate" else "",
        "also": "; ".join(f'{a["type"]}: {a["url"]}' for a in it.get("also", []))[:400],
    })
out.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(sum(r["new"] for r in rows), "new;", len(rows), "rows,", round(out.stat().st_size / 1e6, 2), "MB,", sum(1 for r in rows if r["img"]), "with pictures")
