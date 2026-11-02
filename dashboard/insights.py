"""Market-insight fields for the GCC Product Wall.

1. Google Product Taxonomy category (the global standard Google Shopping and Meta catalogs use).
2. Trend lifecycle stage: Emerging / Growing / Peak / Declining (product life-cycle model).
3. Opportunity score 0-100: a weighted scoring model like the ones product-research tools use
   (demand, cross-platform proof, momentum, price fit, shipping and compliance fit).
Every input is a field already in the tracker; nothing is estimated from outside data.
"""
import math
import re
from pathlib import Path

# ---------------------------------------------------------------- 1. Google Product Taxonomy
# (rule, taxonomy path). First match wins; paths are checked against the official file when present.
GPT_RULES = [
    (r"\bcar\b|vehicle|windshield|sun ?shade|tyre|tire|headrest|backseat|anti-fog|car seat|سيار",
     "Vehicles & Parts > Vehicle Parts & Accessories > Vehicle Maintenance, Care & Decor"),
    (r"seat belt cover", "Vehicles & Parts > Vehicle Parts & Accessories > Vehicle Maintenance, Care & Decor"),
    (r"haircut|shears|thinning scissors|tweezers|scalp|applicator comb", "Health & Beauty > Personal Care > Hair Care"),
    (r"^(?!.*(posture|slimming|back|support|seat|hot sweat)).*\bbelt\b", "Apparel & Accessories > Clothing Accessories > Belts"),
    (r"\bcap\b|\bhat\b", "Apparel & Accessories > Clothing Accessories > Hats"),
    (r"eau de parfum|parfum|fragrance", "Health & Beauty > Personal Care > Cosmetics > Perfume & Cologne"),
    (r"air freshener|moisture absorber|dehumidif", "Home & Garden > Household Supplies"),
    (r"tumbler|straw cup|mug\b|cups?\b", "Home & Garden > Kitchen & Dining > Tableware > Drinkware"),
    (r"seat cushion", "Home & Garden > Decor > Chair & Sofa Cushions"),
    (r"dust mop|\bmop\b", "Home & Garden > Household Supplies > Household Cleaning Supplies"),
    (r"pegs|clothes ?pins", "Home & Garden > Household Supplies > Laundry Supplies"),
    (r"fitted sheet|bed ?sheet|duvet|quilt", "Home & Garden > Linens & Bedding > Bedding"),
    (r"sunglass|uv400|polari[sz]ed|eyewear|نظار", "Apparel & Accessories > Clothing Accessories > Sunglasses"),
    (r"socks", "Apparel & Accessories > Clothing > Underwear & Socks > Socks"),
    (r"innerwear|underwear|brief|boxer|undershirt|\bvests?\b|sirwal|سروال", "Apparel & Accessories > Clothing > Underwear & Socks"),
    (r"abaya|kaftan|thobe|massar|turban|kurta|kurti|saree|dupatta|muslim|عباي",
     "Apparel & Accessories > Clothing > Traditional & Ceremonial Clothing"),
    (r"hijab|scarf|scarves|stole|shawl|حجاب", "Apparel & Accessories > Clothing Accessories > Scarves & Shawls"),
    (r"posture|knee|heel|foot|back pain|brace|drop-foot|support belt",
     "Health & Beauty > Health Care > Supports & Braces"),
    (r"massage", "Health & Beauty > Personal Care > Massage & Relaxation"),
    (r"slimming|shaper|compression|corset|waist", "Apparel & Accessories > Clothing > Underwear & Socks > Shapewear"),
    (r"hair oil|hair\b|شعر", "Health & Beauty > Personal Care > Hair Care"),
    (r"perfume|oud|عطر", "Health & Beauty > Personal Care > Cosmetics > Perfume & Cologne"),
    (r"bakhoor|incense|بخور", "Home & Garden > Decor > Home Fragrances"),
    (r"lash|brow|serum|cream|makeup|skin|laser|callus|beauty|سيروم", "Health & Beauty > Personal Care > Cosmetics"),
    (r"chopper|dicer|cutter|grinder|garlic|peeler|knife|kitchen tool|مفرم",
     "Home & Garden > Kitchen & Dining > Kitchen Tools & Utensils"),
    (r"cooker|egg cooker|spice grinder|juicer|kitchen scale|scale\b",
     "Home & Garden > Kitchen & Dining > Kitchen Appliances"),
    (r"dallah|thermos|bottle|flask", "Home & Garden > Kitchen & Dining > Food & Beverage Carriers"),
    (r"kitchen|مطبخ", "Home & Garden > Kitchen & Dining"),
    (r"hanger|rack|organi[sz]|storage|packing cube|منظم", "Home & Garden > Household Supplies > Storage & Organization"),
    (r"laundry|washing machine", "Home & Garden > Household Supplies > Laundry Supplies"),
    (r"cockroach|bug|insect|pest", "Home & Garden > Household Supplies > Pest Control"),
    (r"towel|cleaning", "Home & Garden > Household Supplies > Household Cleaning Supplies"),
    (r"mattress|cushion cover|bedding|pillow", "Home & Garden > Linens & Bedding"),
    (r"decal|wall|rangoli|toran|decor|kilim|majlis|ornament", "Home & Garden > Decor"),
    (r"door stopper|home repair|tool\b|drill", "Hardware > Tools"),
    (r"watch", "Apparel & Accessories > Jewelry > Watches"),
    (r"jewel|necklace|pendant|bracelet|cuff|brooch|\bring\b|charm", "Apparel & Accessories > Jewelry"),
    (r"tasbih", "Religious & Ceremonial > Religious Items"),
    (r"playing cards", "Toys & Games > Games > Card Games"),
    (r"toy|kids'? .*toy|screen-free|squishy", "Toys & Games > Toys"),
    (r"sticker|notebook|stationery|pencil|wax seal|school", "Office Supplies"),
    (r"phone case|iphone .*case|cases\b", "Electronics > Communications > Telephony > Mobile Phone Accessories > Mobile Phone Cases"),
    (r"tripod|cable|charger|phone", "Electronics > Communications > Telephony > Mobile Phone Accessories"),
    (r"gadget|tech", "Electronics"),
    (r"leggings|workout|activewear", "Apparel & Accessories > Clothing > Activewear"),
    (r"resistance|band set|gym|fitness|yoga", "Sporting Goods > Exercise & Fitness"),
    (r"pool", "Sporting Goods > Outdoor Recreation"),
    (r"gift bag|wrap|eid gift|gift", "Arts & Entertainment > Party & Celebration > Gift Giving"),
    (r"umbrella", "Apparel & Accessories > Clothing Accessories"),
    (r"toiletry|makeup organi[sz]er bag|travel", "Luggage & Bags"),
    (r"handbag|bag\b", "Apparel & Accessories > Handbags, Wallets & Cases > Handbags"),
    (r"coffee|chocolate|food|snack", "Food, Beverages & Tobacco"),
    (r"slides|slipper|shoes|sandals", "Apparel & Accessories > Shoes"),
    (r"t-shirt|shirt|tee\b|pants|dress|kimono|jacket|outfit|clothing|wear\b", "Apparel & Accessories > Clothing"),
]

_TAXO = None


def taxonomy():
    """{path: id} from the saved Google Product Taxonomy file, or {} if it is missing."""
    global _TAXO
    if _TAXO is None:
        _TAXO = {}
        f = Path(__file__).resolve().parent / "google_taxonomy.txt"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if " - " in line and not line.startswith("#"):
                    gid, path = line.split(" - ", 1)
                    _TAXO[path.strip()] = gid.strip()
    return _TAXO


def google_category(text):
    """(top-level, full path, id) for a product name. The path is trimmed to the deepest level the
    official file contains, so a guessed sub-level never shows up as if it were official."""
    tax = taxonomy()
    for pat, path in GPT_RULES:
        if re.search(pat, text, re.I):
            if tax:
                parts = path.split(" > ")
                while parts and " > ".join(parts) not in tax:
                    parts.pop()
                if parts:
                    path = " > ".join(parts)
                    return path.split(" > ")[0], path, tax[path]
            else:
                return path.split(" > ")[0], path, ""
    return "Other", "", ""


# ---------------------------------------------------------------- 2. Lifecycle stage
def lifecycle(it, today, pdate):
    t = it.get("type")
    if t == "Amazon":
        mv = str(it.get("movement", "")).lower()
        rank = num(it.get("rank"))
        was = re.search(r"(?:was|from) #(\d+)", mv)
        if "new in top" in mv or "new release" in mv:
            return "Emerging"
        if was and rank is not None:
            return "Growing" if rank < int(was.group(1)) else ("Declining" if rank > int(was.group(1)) + 2 else "Peak")
        if "down" in mv:
            return "Declining"
        if "up" in mv:
            return "Growing"
        return "Peak" if rank is not None and rank <= 10 else ""
    if t == "Meta ad":
        d = num(it.get("days"))
        if d is None:
            return ""
        return "Emerging" if d < 30 else "Growing" if d < 90 else "Peak" if d < 270 else "Declining"
    if t in ("YouTube", "Video product"):
        pub = pdate(it.get("published")) or pdate(it.get("date"))
        if not pub:
            return ""
        age = max((today - pub).days, 1)
        return "Emerging" if age <= 14 else "Growing" if age <= 60 else "Peak"
    if t == "TikTok ad":  # in TikTok's top-ads list now: new this month, or still there weeks later
        first, seen = pdate(it.get("first_date")), pdate(it.get("date"))
        if not first or not seen or first >= seen:
            return ""  # seen in one scan only: no trend reading yet
        return "Growing" if (today - first).days > 14 else "Emerging"
    if t == "Candidate":
        shape = str(it.get("trend", "")).lower()
        return {"rising": "Growing", "seasonal": "Peak", "flat": "Peak", "declining": "Declining"}.get(shape, "")
    return ""


# ---------------------------------------------------------------- 3. Opportunity score
GATE_FAIL = re.compile(r"gate fail|battery|liquid|electric|glass|heavy|bulky|medical|weight-loss|risky|food|over 400", re.I)
GATE_PASS = re.compile(r"gate pass|india .*fit|light", re.I)
STAGE_PTS = {"Emerging": 90, "Growing": 100, "Peak": 60, "Declining": 15, "": 45}
WEIGHTS = {"demand": 0.25, "proof": 0.15, "momentum": 0.15, "price": 0.15, "fit": 0.20, "trade": 0.10}

# Product name -> HS code (4-digit customs group) used in the "India Exports to GCC" tab.
HS_RULES = [
    (r"corset|shaper|shapewear|compression|slimming|waist", "6212"),
    (r"socks", "6115"),
    (r"innerwear|underwear|brief|boxer|undershirt|\bvests?\b|sirwal|سروال", "6107"),
    (r"t-shirt|tee\b|\bshirt", "6109"),
    (r"kurta|palazzo|dress", "6104"),
    (r"abaya|kaftan|kimono|outer layer|thobe|عباي", "6211"),
    (r"hijab|scarf|scarves|stole|shawl|massar|turban|dupatta|حجاب", "6214"),
    (r"posture|knee|heel|foot support|brace|drop-foot|back pain", "9021"),
    (r"sunglass|uv400|polari[sz]ed|eyewear", "9004"),
    (r"jewel|necklace|pendant|bracelet|cuff|brooch|\bring\b|charm", "7117"),
    (r"bag|organi[sz]er bag|toiletry|wallet|pouch|luggage", "4202"),
    (r"cushion cover|sheet|bedding|pillow|kilim|majlis", "6304"),
    (r"sun ?shade|car seat|organi[sz]|packing cube|storage", "6307"),
    (r"hanger|plastic|rack|trash can|pegs", "3926"),
    (r"chopper|grater|garlic|dicer|cutter|peeler", "8205"),
    (r"spoon|ladle|kitchen tool|utensil", "8215"),
    (r"bakhoor|incense|oud\b|room perfume|بخور", "3307"),
    (r"wood|sheesham|massage roller", "4421"),
    (r"slides|slipper|sandals", "6405"),
    (r"toy|squishy|playing cards", "9503"),
]


def hs_code(text):
    for pat, code in HS_RULES:
        if re.search(pat, text, re.I):
            return code
    return ""


def trade_points(change):
    if change in ("", None):
        return 45
    c = float(change)
    return 100 if c >= 25 else 75 if c >= 10 else 55 if c >= 0 else 35 if c > -15 else 10


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def demand(it):
    """0-100 within each source's own scale."""
    t = it.get("type")
    if t in ("YouTube", "Video product"):
        v = num(it.get("views")) or 0
        return min(100, max(0, (math.log10(v + 1) - 4) / 3 * 100))      # 10K views = 0, 10M = 100
    if t == "Meta ad":
        d = num(it.get("days")) or 0
        return min(100, d / 180 * 100)                                    # 180+ days running = proven
    if t == "Amazon":
        r = num(it.get("rank")) or 30
        rev = num(it.get("reviews")) or 0
        return min(100, max(0, (31 - r) / 30 * 70) + min(30, math.log10(rev + 1) / 4 * 30))
    if t == "Candidate":
        return min(100, 35 * (num(it.get("signals")) or 1))
    if t == "TikTok ad":  # a top auction ad in that country; likes 10 = 0 .. 10K = 70, plus up to 30 for CTR
        lk = num(it.get("likes")) or 0
        ctr = num(it.get("ctr")) or 0
        return min(100, max(0, (math.log10(lk + 1) - 1) / 3 * 70) + min(30, ctr * 15))
    return 30


def price_fit(it):
    m = num(it.get("margin"))
    if m is not None:  # a real margin from our own India cost beats a price-range guess
        return 100 if m >= 50 else 75 if m >= 35 else 40 if m >= 20 else 10
    p = num(it.get("price"))
    if p is None:
        return 45
    if 69 <= p <= 149:
        return 100
    if 40 <= p < 69:
        return 70   # bundle 2-3 to reach the range
    if 149 < p <= 199:
        return 60
    return 20


def ship_fit(it):
    note = str(it.get("note", "")) + " " + str(it.get("title", ""))
    if GATE_FAIL.search(note):
        return 0
    w = num(it.get("weight"))
    if w is not None:
        return 100 if w < 400 else 10
    return 80 if GATE_PASS.search(note) else 55


VENDOR = re.compile(r"vendor claim|not gcc-verified|global, not|global only", re.I)
MEASURED = re.compile(r"tracker|amazon\.|noon\.|ads/library|ad library|best sellers|instagram pulse|youtube gcc|marketplace signals|"
                      r"gcc ad signals|views|days running|reviews", re.I)


def evidence(it):
    """How trustworthy a candidate's evidence is: (multiplier, label). Measured platform data counts fully,
    press and platform reports 75%, vendor marketing claims or global-only data 50%."""
    if it.get("type") != "Candidate":
        return 1.0, "measured"
    text = str(it.get("note", "")) + " " + str(it.get("url", ""))
    if MEASURED.search(text) and VENDOR.search(text):
        return 0.75, "mixed: measured + vendor claim"
    if MEASURED.search(text):
        return 1.0, "measured"
    if VENDOR.search(text):
        return 0.5, "vendor claim"
    if text.strip():
        return 0.75, "press / report"
    return 0.5, "none recorded"


# Courier cost assumptions for price fit when our own cost is not known yet. Overwritten from the sheet's
# "Shipping Rates" tab (dashboard/shipping.json) by build_wall.py.
SHIPPING = {"inr_per_aed": 25.86, "gst": 0.18, "fuel_per_kg": 47, "packaging": 0,
            "slabs": [[500, 1259], [1000, 1470], [2000, 1700], [3000, 2000], [5000, 3090], [10000, 4400]]}


def courier_aed(weight_g):
    """Courier charge in AED for one parcel (rate for the weight slab + GST + fuel surcharge)."""
    w = weight_g or 500  # unknown weight: assume the smallest slab (most of our products are under 500 g)
    base = next((r for lim, r in SHIPPING["slabs"] if w <= lim), SHIPPING["slabs"][-1][1])
    inr = base * (1 + SHIPPING["gst"]) + SHIPPING["fuel_per_kg"] * max(0.5, math.ceil(w / 500) / 2) + SHIPPING["packaging"]
    return inr / SHIPPING["inr_per_aed"]


def price_fit_after_shipping(it):
    """Without our own cost, judge price by how much is left after the courier charge (headroom for the
    product cost and margin). A real margin from the Candidates sheet always wins."""
    m = num(it.get("margin"))
    if m is not None:
        return 100 if m >= 50 else 75 if m >= 35 else 40 if m >= 20 else 10
    p = num(it.get("price"))
    rng = re.findall(r"\d+(?:\.\d+)?", str(it.get("price_label", ""))) if it.get("type") == "Candidate" else []
    if len(rng) >= 2:  # a range such as "AED 69-109": judge at the middle of the range
        p = (float(rng[0]) + float(rng[1])) / 2
    if p is None or p <= 0:
        return None
    left = (p - courier_aed(num(it.get("weight")))) / p
    return 100 if left >= 0.60 else 75 if left >= 0.45 else 40 if left >= 0.30 else 10


# Confidence pulls a score toward the middle (50): a strong score on thin evidence should not outrank a
# good score on solid evidence.
SHRINK = {"High": 1.0, "Medium": 0.85, "Low": 0.6}


def shrink(factors_known, conf):
    """Combined pull toward 50: lower confidence and fewer known factors (out of 6) both count."""
    return SHRINK[conf] * min(1.0, 0.55 + 0.1 * factors_known)


def score(it, proof_sources, trade_change=None):
    """Weighted 0-100 score over the factors we actually know for this product. Unknown factors (no price,
    no weight, no trend reading, no export data) are left out and the remaining weights rescaled, instead
    of being filled with a neutral guess. Returns (score, parts, factors_known)."""
    q, _ = evidence(it)
    parts = {"demand": demand(it) * q, "proof": min(100, 25 * proof_sources) * q}
    if it.get("stage"):
        parts["momentum"] = STAGE_PTS.get(it.get("stage"), 45)
    pf = price_fit_after_shipping(it)
    if pf is not None:
        parts["price"] = pf
    note = str(it.get("note", "")) + " " + str(it.get("title", ""))
    if GATE_FAIL.search(note):
        parts["fit"] = 0
    elif num(it.get("weight")) is not None or GATE_PASS.search(note):
        fit = ship_fit(it)
        parts["fit"] = 80 if it.get("type") == "Candidate" and fit == 100 else fit  # candidate weight is our estimate
    if trade_change not in ("", None):
        parts["trade"] = trade_points(trade_change)
    wsum = sum(WEIGHTS[k] for k in parts)
    total = round(sum(parts[k] * WEIGHTS[k] for k in parts) / wsum)
    return total, {k: round(v) for k, v in parts.items()}, len(parts)
