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
# Product category from the title (plus Amazon's category where given). First match wins.
CATS = [
    ("Car accessories", r"\bcar\b|vehicle|windshield|tyre|tire|seat cushion|headrest|backseat|anti-fog|سيار"),
    ("Sunglasses & eyewear", r"sunglass|uv400|polari[sz]ed|eyewear|نظار"),
    ("Innerwear & socks", r"innerwear|underwear|brief|boxer|socks|vest|sirwal|سروال|undershirt"),
    ("Modest & traditional wear", r"abaya|hijab|scarf|scarves|kaftan|kurta|kurti|thobe|massar|turban|stole|shawl|dupatta|saree|muslim|عباي|حجاب"),
    ("Health & body support", r"posture|knee|heel|foot|back pain|brace|support belt|slimming|compression|corset|massage|callus|pain|shaper|ركب|كعب|ظهر"),
    ("Beauty & personal care", r"hair|lash|brow|serum|cream|oil|perfume|oud|bakhoor|incense|skin|makeup|laser|beauty|سيروم|عطر|بخور"),
    ("Kitchen", r"kitchen|chopper|dicer|grinder|cutter|cooker|egg|spice|garlic|juicer|knife|dallah|thermos|bottle|scale|مطبخ|مفرم"),
    ("Home & organisation", r"organi[sz]|storage|rack|hanger|laundry|cleaning|door|cushion cover|mattress|decal|wall|towel|cockroach|bug|home|majlis|kilim|pool|shoe rack|washing machine|منظم|بيت"),
    ("Jewellery & watches", r"jewel|necklace|pendant|bracelet|cuff|brooch|ring\b|watch|tasbih|charm"),
    ("Kids, toys & school", r"kid|toy|school|stationery|sticker|pencil|notebook|baby|girls|playing cards"),
    ("Phones & gadgets", r"phone|iphone|cable|charger|tripod|gadget|tech|speaker|tv\b"),
    ("Fitness & sport", r"gym|workout|leggings|resistance|band set|yoga|fitness|cycling"),
    ("Gifts & seasonal", r"gift|eid|diwali|national day|rangoli|toran|wrap|ramadan"),
    ("Travel", r"travel|umbrella|packing cube|luggage|toiletry"),
    ("Food & drink", r"coffee|chocolate|food|snack|tea\b|dates\b"),
    ("Clothing & footwear", r"shirt|t-shirt|tee|pants|dress|wear|slides|slipper|shoes|jacket|kimono|outfit|handbag|bag|belt"),
]
import re as _re
def category(it):
    text = " ".join(str(it.get(k, "")) for k in ("title", "category", "keyword"))
    for name, pat in CATS:
        if _re.search(pat, text, _re.I):
            return name
    return "Mixed product videos" if it.get("type") == "YouTube" else "Other"

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
        "video": it.get("video", "") or "",
        "ref": bool(it.get("ref")), "ref_url": it.get("ref_url", "") or "",
        "category": category(it),
    })
out.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(sum(r["new"] for r in rows), "new;", len(rows), "rows,", round(out.stat().st_size / 1e6, 2), "MB,", sum(1 for r in rows if r["img"]), "with pictures")
