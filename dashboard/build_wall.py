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
# ---- History: every dated sighting of the same product, from the sheet's repeat scans and from the
# weekly snapshots the export job saves in dashboard/history/. Used for trend lines and week-on-week change.
METRIC = {"Amazon": "rank", "Meta ad": "days", "TikTok ad": "likes", "YouTube": "views", "Video product": "views", "Candidate": "signals"}
def hkey(it):
    if it["type"] == "Candidate" or not it.get("url"):
        return (it["type"], re.sub(r"\W+", "", str(it.get("title", "")).lower())[:40])
    return (it["type"], it.get("url"))
import re
SERIES = {}
def add_point(it, d):
    m = METRIC.get(it["type"])
    v = it.get(m) if m else None
    if d is None or v in (None, ""):
        return
    SERIES.setdefault(hkey(it), {})[d.strftime("%Y-%m-%d")] = {"v": v, "price": it.get("price")}
for it in items:
    add_point(it, pdate(it.get("date")) if it["type"] != "YouTube" else pdate(it.get("date")))
_hd = repo / "dashboard" / "history"
if _hd.exists():
    for f in sorted(_hd.glob("*.json")):
        d = pdate(f.stem)
        for it in json.loads(f.read_text(encoding="utf-8")):
            add_point(it, d)

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
ORDER = {"Candidate": 0, "Amazon": 1, "Meta ad": 2, "TikTok ad": 3, "Video product": 4}
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
SRC = {"Amazon": "Marketplace", "Meta ad": "Meta ads", "TikTok ad": "TikTok ads", "YouTube": "YouTube", "Video product": "YouTube", "Candidate": "Candidates"}
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
_sf = repo / "dashboard" / "shipping.json"
if _sf.exists():
    insights.SHIPPING.update(json.loads(_sf.read_text(encoding="utf-8")))
TRADE = {}
_tf = repo / "dashboard" / "trade.json"
if _tf.exists():
    for t in json.loads(_tf.read_text(encoding="utf-8")):
        # Growth from a tiny base (under USD 1M a year) says little about the market: left out.
        if t.get("change") not in ("", None) and (insights.num(t.get("usd")) or 0) >= 1_000_000:
            TRADE[(str(t["hs"]), t["country"])] = float(t["change"])
for it in items:
    it["hs"] = insights.hs_code(" ".join(str(it.get(k, "")) for k in ("title", "keyword")))
    cs = [c for c in it.get("countries", []) if c in ("UAE", "Saudi Arabia", "Kuwait", "Qatar", "Oman")] or ["UAE", "Saudi Arabia", "Kuwait", "Qatar", "Oman"]
    vals = [(TRADE[(it["hs"], c)], c) for c in cs if (it["hs"], c) in TRADE]
    best = max(vals) if vals else None
    it["trade_change"] = best[0] if best else None
    it["trade_country"] = best[1] if best else ""
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
        it["score"], it["score_parts"], it["factors"] = None, {}, 0
    else:
        it["score"], it["score_parts"], it["factors"] = insights.score(it, len(srcs), it["trade_change"])

def hist_of(it):
    pts = SERIES.get(hkey(it), {})
    return [[d, pts[d]["v"]] for d in sorted(pts)][-12:]


def change_of(it):
    h = hist_of(it)
    if len(h) < 2:
        return ""
    (d0, a), (d1, b) = h[-2], h[-1]
    when = datetime.strptime(d0, "%Y-%m-%d").strftime("%d %b")
    if it["type"] == "Amazon":
        a, b = int(a), int(b)
        return f"Rank #{a} → #{b} since {when}" + (f" (up {a - b})" if b < a else f" (down {b - a})" if b > a else " (steady)")
    if it["type"] in ("YouTube", "Video product"):
        return f"+{int(b) - int(a):,} views since {when}" if b >= a else ""
    if it["type"] == "Candidate":
        return f"Signals {int(a)} → {int(b)} since {when}" if a != b else ""
    return f"Still running on {datetime.strptime(d1, '%Y-%m-%d').strftime('%d %b')} (first seen running {when})"


MEASURES = {
    "Amazon": "Marketplace rank in that country's store (measured; rank, not units sold)",
    "Meta ad": "Days an ad has been live (measured; shows a seller keeps paying, not how much it sells)",
    "YouTube": "Video views worldwide; found by a search set to that country (viewers may be anywhere)",
    "Video product": "Views of the video that names the product (worldwide)",
    "Candidate": "Our shortlist entry: evidence gathered from the sources noted",
    "TikTok ad": "One of TikTok's top auction ads in that country over 30 days (measured by TikTok; likes and CTR, not sales)",
}


def confidence(it):
    pts = 0
    if it["type"] in ("Amazon", "Meta ad", "TikTok ad") or (it["type"] == "Candidate" and insights.evidence(it)[0] >= 1.0):
        pts += 1
    if it.get("price") not in (None, ""):
        pts += 1
    if len(hist_of(it)) >= 2 or len(it.get("proof_sources", [])) >= 2:
        pts += 1
    cs = [c for c in it.get("countries", []) if c]
    if cs and len(cs) <= 2 and it["type"] != "YouTube":
        pts += 1
    return "High" if pts >= 4 else "Medium" if pts >= 2 else "Low"


# Meta audience (people Meta can reach per month) for the interest closest to the product's category.
AUD_MAP = [(r"Scarves|Shawl", ["Hijab", "Shawl"]), (r"Traditional", ["Abaya", "Kurta"]),
           (r"Supports & Braces|Massage", ["Back pain"]), (r"Cushion|Linens", ["Cushion"]),
           (r"Jewelry", ["Costume jewelry"]), (r"Sunglasses", ["Sunglasses"]), (r"Kitchen", ["Kitchen utensil"]),
           (r"Luggage", ["Travel"]), (r"Perfume|Fragrance", ["Perfume"]),
           (r"Shoes", ["Shoes"]), (r"Hardware|Household", ["Home improvement"])]
AUD = {}
_af = repo / "dashboard" / "audience.json"
if _af.exists():
    for a in json.loads(_af.read_text(encoding="utf-8")):
        if a.get("high"):
            AUD[(a["country"], a["term"])] = a


def audience_of(it):
    path = it.get("gpath") or it.get("gcat") or ""
    terms = next((t for rx, t in AUD_MAP if re.search(rx, path)), None)
    if not terms:
        return None, ""
    cs = [c for c in it.get("countries", []) if c in ("UAE", "Saudi Arabia", "Kuwait", "Qatar", "Oman")] or \
         ["UAE", "Saudi Arabia", "Kuwait", "Qatar", "Oman"]
    best = None
    for t in terms:
        tot = sum(AUD[(c, t)]["high"] for c in cs if (c, t) in AUD)
        if tot and (best is None or tot > best[0]):
            best = (tot, t, AUD[(next(c for c in cs if (c, t) in AUD), t)]["interest"])
    if not best:
        return None, ""
    return int(best[0]), f"Meta interest '{best[2]}', {', '.join(cs) if len(cs) < 5 else 'all 5 countries'}"


# ---- Demand without ads: products with measured demand where none of the ads we track (Meta Ad Library,
# TikTok Top Ads) are for the same kind of product in the same country. Our ad data is a sample (the
# Meta scan searches set keywords, TikTok shows ~20 top ads per list), so "no ads seen" is a lead to check,
# not proof. A targeted Meta Ad Library search in the Monday scan confirms it ("Ad Gap Checks" tab).
STOP = set("with from pack pcs piece pieces set sets for and the men's women's mens womens kids girls boys new "
           "best size large small cotton black white color colour inch premium quality original pair pairs".split())


def keywords(text):
    return {w for w in re.findall(r"[a-z]{4,}", str(text).lower()) if w not in STOP}


def same_kind(p1, p2):
    """Same product type: identical Google category, or one inside the other when the broader one is at
    least 3 levels deep (Underwear & Socks contains Socks; plain 'Clothing' is too broad to count)."""
    if not p1 or not p2:
        return False
    a, b = p1.split(" > "), p2.split(" > ")
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return a == b or (len(short) >= 3 and long_[:len(short)] == short)


ADS = [it for it in items if it["type"] in ("Meta ad", "TikTok ad")]
for a in ADS:
    a["_kw"] = keywords(a.get("title", ""))
    a["_cs"] = set(c for c in a.get("countries", []) if c) or {"GCC"}


def demand_evidence(it):
    """Plain-language demand proof for products we can measure, or None."""
    t = it["type"]
    if t == "Amazon":
        rank, rev = insights.num(it.get("rank")), insights.num(it.get("reviews"))
        bits = []
        if rank is not None and rank <= 10:
            bits.append(f"#{int(rank)} in {it.get('source', 'Amazon')}")
        if rev is not None and rev >= 300:
            bits.append(f"{int(rev):,} reviews")
        return " · ".join(bits) or None
    if t == "Video product":
        v = insights.num(it.get("views"))
        return f"{int(v):,} views on a shopping video" if v and v >= 200_000 else None
    if t == "Candidate":
        q, label = insights.evidence(it)
        sig = insights.num(it.get("signals")) or 0
        return f"{int(sig)} independent signals ({label})" if q >= 1.0 and sig >= 2 else None
    return None


CONFIRM = {}
_cf = repo / "dashboard" / "adgap_checks.json"
if _cf.exists():
    for c in json.loads(_cf.read_text(encoding="utf-8")):
        CONFIRM[(str(c.get("product", "")).strip().lower(), c.get("country", ""))] = c

for it in items:
    it["no_ads"], it["ads_near"] = False, 0
    ev = demand_evidence(it)
    if not ev or it.get("score") is None or it["score"] < 50:
        continue
    cs = set(c for c in it.get("countries", []) if c) or {"GCC"}
    kw = keywords(it.get("title", ""))
    near = [a for a in ADS if (a["_cs"] & cs or "GCC" in a["_cs"] or "GCC" in cs)
            and (same_kind(a.get("gpath"), it.get("gpath")) or (kw & a["_kw"]))]
    it["ads_near"] = len(near)
    it["demand_ev"] = ev
    if not near:
        it["no_ads"] = True
        chk = next((CONFIRM[k] for k in CONFIRM if k[0] == str(it.get("title", "")).strip().lower()), None)
        if chk:
            found = insights.num(chk.get("ads"))
            it["adcheck"] = (f"Meta Ad Library check {chk.get('date', '')}: {chk.get('ads')} active ads for "
                             f"'{chk.get('keyword', '')}' in {chk.get('country', '')}")
            if found:  # the targeted search found ads: not a gap after all
                it["no_ads"], it["ads_near"] = False, int(found)

for it in items:
    if it.get("score") is not None:
        it["score_raw"] = it["score"]
        it["score"] = round(50 + (it["score"] - 50) * insights.shrink(it.get("factors", 6), confidence(it)))

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
    elif it["type"] == "TikTok ad":
        fs = pdate(it.get("first_date")) or pdate(it.get("date"))
    else:
        fs = it.get("first_seen")
    is_new = bool(fs and fs >= week_ago)
    rows.append({"new": is_new, "first_seen": fs.strftime("%Y-%m-%d") if fs else "",
        "id": it["id"], "type": it["type"], "title": str(it.get("title", "")).strip(),
        "url": it.get("url", ""), "country": ", ".join(cs) or "GCC",
        "source": str(it.get("source", "")), "price": it.get("price"),
        "price_label": it.get("price_label", "") or "",
        "views": it.get("views"), "likes": it.get("likes"), "ctr": it.get("ctr"), "industry": it.get("industry", ""), "days": it.get("days"),
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
        "hs": it["hs"], "trade_change": it["trade_change"], "trade_country": it.get("trade_country", ""),
        "score_raw": it.get("score_raw"), "factors": it.get("factors", 0),
        "no_ads": it.get("no_ads", False), "ads_near": it.get("ads_near", 0), "demand_ev": it.get("demand_ev", ""),
        "adcheck": it.get("adcheck", ""),
        "proof_sources": ", ".join(it["proof_sources"]),
        "margin": it.get("margin"), "india_cost": it.get("india_cost"),
        "hist": hist_of(it), "change": change_of(it), "confidence": confidence(it),
        "measures": MEASURES.get(it["type"], ""), "aud": audience_of(it)[0], "aud_label": audience_of(it)[1],
        "evidence": insights.evidence(it)[1] if it["type"] == "Candidate" else "",
        "also": "; ".join(f'{a["type"]}: {a["url"]}' for a in it.get("also", []))[:400],
    })
out.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(sum(r["new"] for r in rows), "new;", len(rows), "rows,", round(out.stat().st_size / 1e6, 2), "MB,", sum(1 for r in rows if r["img"]), "with pictures")
