"""Creative Playbook: what the best-performing Gulf posts and ads have in common.

Reads the tracker's own tabs (TikTok Videos, TikTok Top Ads, Gulf Shop Posts, Instagram Pulse) and compares
posts that have a feature (price shown, cash-on-delivery, discount, question hook...) with posts that do not.
Engagement is always compared within one source, never across sources:
  - Instagram shop posts: likes against that shop's own average (removes the size of the shop)
  - TikTok hashtag videos: views
  - TikTok top ads: TikTok's CTR figure
Each line states its sample size; lines with fewer than MIN_N posts on either side are left out.
Correlation, not cause: a feature common in strong posts is a thing to test, not a guarantee.
"""
import re
import statistics
from datetime import datetime

MIN_N = 5
HEADERS = ["Section", "Finding", "Source", "With (median)", "Without (median)", "Lift", "Read as", "Posts with / without",
           "Example", "Example link", "Week of"]
# Global hashtags whose videos come from everywhere: left out so they do not swamp the Gulf comparison.
GLOBAL_TAGS = {"#tiktokmademebuyit"}

FEATURES = [
    ("Shows a price", re.compile(r"\d+\s*(?:aed|sar|qar|kwd|omr|درهم|ريال|دينار|ر\.س|د\.إ)|(?:aed|sar|qar|kwd|omr)\s*\d+", re.I)),
    ("Mentions cash on delivery", re.compile(r"الدفع عند الاستلام|عند الاستلام|cash on delivery|\bcod\b", re.I)),
    ("Mentions free delivery", re.compile(r"توصيل مجاني|شحن مجاني|free (?:delivery|shipping)", re.I)),
    ("Discount or offer", re.compile(r"خصم|تخفيض|عرض|عروض|\d+\s*%|\bsale\b|\boff\b|discount|offer", re.I)),
    ("Opens with a question", re.compile(r"^[^\n]{0,80}[?؟]")),
    ("Call to order / DM / WhatsApp", re.compile(r"اطلب|للطلب|واتس|whatsapp|\bdm\b|order now|link in bio|الرابط", re.I)),
    ("Written in Arabic", re.compile(r"[؀-ۿ]{3,}")),
    ("Mentions a gift", re.compile(r"هدية|هدايا|\bgift", re.I)),
    ("Before/after or demo wording", re.compile(r"قبل وبعد|before.{0,10}after|تجربة|جربت|review|مراجعة|how to|طريقة", re.I)),
]
GIVEAWAY = re.compile(r"giveaway|give away|contest|win a|chance to win|مسابق|سحب|يفوز|تفوز|اربح", re.I)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _when(v):
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(v).strip()[:16], f)
        except ValueError:
            pass
    return None


def _fmt(v, kind):
    if v is None:
        return ""
    if kind == "ctr":
        return f"{v:.2f}"
    if kind == "x":
        return f"{v:.2f}×"
    return f"{v:,.0f}"


def _posts(book_rows):
    """Normalise each source into {source, kind, metric, caption, when, link, extra}."""
    out = []
    for r in book_rows.get("Gulf Shop Posts", []):
        cap = str(r.get("Caption", ""))
        if str(r.get("Giveaway", "")).lower() == "yes" or GIVEAWAY.search(cap):
            continue
        out.append({"source": "Instagram shop posts", "kind": "x", "metric": _num(r.get("Likes vs shop average (x)")),
                    "caption": cap, "when": _when(r.get("Posted (Gulf time)")), "link": r.get("Link", ""),
                    "media": str(r.get("Media type", ""))})
    seen = set()
    for r in book_rows.get("TikTok Videos", []):
        if str(r.get("Hashtag", "")).lower() in GLOBAL_TAGS or r.get("Link") in seen:
            continue
        seen.add(r.get("Link"))
        out.append({"source": "TikTok hashtag videos", "kind": "views", "metric": _num(r.get("Views")),
                    "caption": str(r.get("Caption", "")), "when": _when(r.get("Posted (Gulf time)")),
                    "link": r.get("Link", ""), "media": "VIDEO"})
    from .export import FOREIGN_SCRIPT, TT_NOT_PRODUCT, tt_industry
    seen = set()
    for r in book_rows.get("TikTok Top Ads", []):
        title = str(r.get("Ad title", ""))
        if (r.get("Ad ID") in seen or not tt_industry(r.get("Industry", "")) or FOREIGN_SCRIPT.search(title)
                or TT_NOT_PRODUCT.search(title)):
            continue
        seen.add(r.get("Ad ID"))
        out.append({"source": "TikTok top ads", "kind": "ctr", "metric": _num(r.get("CTR (TikTok)")),
                    "caption": str(r.get("Ad title", "")), "when": None, "link": r.get("Link", ""),
                    "media": "VIDEO", "length": _num(r.get("Video length (s)"))})
    return [p for p in out if p["metric"] is not None and p["caption"].strip()]


def build(book_rows, week):
    posts = _posts(book_rows)
    rows = []
    sources = sorted({p["source"] for p in posts})

    # 1) Caption features: median engagement with vs without, per source.
    for src in sources:
        ps = [p for p in posts if p["source"] == src]
        kind = ps[0]["kind"]
        for name, rx in FEATURES:
            yes = [p for p in ps if rx.search(p["caption"])]
            no = [p for p in ps if not rx.search(p["caption"])]
            if len(yes) < MIN_N or len(no) < MIN_N:
                continue
            my, mn = statistics.median(p["metric"] for p in yes), statistics.median(p["metric"] for p in no)
            lift = (my / mn - 1) if mn else None
            ex = max(yes, key=lambda p: p["metric"])
            read = ("Strong pattern" if lift is not None and abs(lift) >= 0.25 and min(len(yes), len(no)) >= 10
                    else "Some pattern" if lift is not None and abs(lift) >= 0.10 else "No clear difference")
            rows.append(["Caption features", name, src, _fmt(my, kind), _fmt(mn, kind),
                         "" if lift is None else f"{lift:+.0%}", read, f"{len(yes)} / {len(no)}",
                         " ".join(ex["caption"].split())[:140], ex["link"], week])

    # 2) Format: Instagram reels vs photos vs carousels.
    ig = [p for p in posts if p["source"] == "Instagram shop posts"]
    for media in ("VIDEO", "IMAGE", "CAROUSEL_ALBUM"):
        ms = [p for p in ig if p["media"] == media]
        if len(ms) >= MIN_N:
            rows.append(["Format", {"VIDEO": "Reel / video", "IMAGE": "Single photo", "CAROUSEL_ALBUM": "Carousel"}[media],
                         "Instagram shop posts", _fmt(statistics.median(p["metric"] for p in ms), "x"), "", "", "",
                         f"{len(ms)}", "", "", week])

    # 3) Posting time (Gulf time): best day and best 3-hour window by median engagement, per source.
    for src in sources:
        ps = [p for p in posts if p["source"] == src and p["when"]]
        if len(ps) < 3 * MIN_N:
            continue
        kind = ps[0]["kind"]
        for label, key in (("Day of week", lambda p: DAYS[p["when"].weekday()]),
                           ("Time of day (Gulf)", lambda p: f"{p['when'].hour // 3 * 3:02d}:00–{p['when'].hour // 3 * 3 + 3:02d}:00")):
            groups = {}
            for p in ps:
                groups.setdefault(key(p), []).append(p["metric"])
            ranked = sorted(((statistics.median(v), k, len(v)) for k, v in groups.items() if len(v) >= MIN_N), reverse=True)
            for med, k, n in ranked[:3]:
                rows.append(["Posting time", f"{label}: {k}", src, _fmt(med, kind), "", "", "", f"{n}", "", "", week])

    # 4) Video length for TikTok top ads (by CTR).
    ads = [p for p in posts if p["source"] == "TikTok top ads" and p.get("length")]
    buckets = [(0, 10, "Up to 10 s"), (10, 20, "11–20 s"), (20, 30, "21–30 s"), (30, 60, "31–60 s"), (60, 10**6, "Over 60 s")]
    for lo, hi, name in buckets:
        b = [p for p in ads if lo < p["length"] <= hi]
        if len(b) >= MIN_N:
            rows.append(["Video length", name, "TikTok top ads", _fmt(statistics.median(p["metric"] for p in b), "ctr"),
                         "", "", "", f"{len(b)}", "", "", week])

    # 5) Hooks: opening words of the top posts in each source, to copy the structure (not the words).
    for src in sources:
        ps = sorted((p for p in posts if p["source"] == src), key=lambda p: -p["metric"])[:6]
        for p in ps:
            hook = " ".join(re.split(r"[\n.!؟?]", p["caption"].strip())[0].split()[:14])
            rows.append(["Top hooks", hook[:120], src, _fmt(p["metric"], p["kind"]), "", "", "", "", "", p["link"], week])

    # 6) Hashtags used most by the top quarter of TikTok videos.
    tt = sorted((p for p in posts if p["source"] == "TikTok hashtag videos"), key=lambda p: -p["metric"])
    top = tt[: max(1, len(tt) // 4)]
    counts = {}
    for p in top:
        for h in set(re.findall(r"#[\w؀-ۿ]+", p["caption"])):
            counts[h.lower()] = counts.get(h.lower(), 0) + 1
    for h, n in sorted(counts.items(), key=lambda kv: -kv[1])[:15]:
        if n >= 3:
            rows.append(["Hashtags in top TikTok videos", h, "TikTok hashtag videos", "", "", "", "", f"{n} of {len(top)}",
                         "", "", week])
    return rows
