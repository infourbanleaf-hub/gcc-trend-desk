"""Export tracker rows + product pictures for the visual dashboard.

Reads the Product Discovery Tracker, picks product rows (candidates, Amazon best sellers,
Meta COD ads, product-search YouTube videos), fetches a small picture for each where one is
publicly available, and writes dashboard/data.json + dashboard/img/*.jpg.
"""
import hashlib
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/129.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
TO_AED = {"AED": 1.0, "SAR": 0.979, "QAR": 1.009, "OMR": 9.54, "KWD": 11.95, "BHD": 9.74}
COUNTRIES = {"UAE": ["uae", "dubai", "abu dhabi", "amazon.ae", "emirat"],
             "Saudi Arabia": ["saudi", "ksa", "riyadh", "jeddah", "amazon.sa"],
             "Kuwait": ["kuwait"], "Qatar": ["qatar", "doha"], "Oman": ["oman", "muscat"]}


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def price_aed(text):
    """'SAR 39.99' -> 39.15 ; '79-129' -> 79 ; 'AED 37.05' -> 37.05."""
    s = str(text or "")
    s = s.replace(",", "")
    m = re.search(r"(AED|SAR|QAR|OMR|KWD|BHD)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(AED|SAR|QAR|OMR|KWD|BHD)", s.upper())
    if m:
        cur, val = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        return round(float(val) * TO_AED[cur], 2)
    m = re.findall(r"\d+(?:\.\d+)?", s)
    return round(float(m[0]), 2) if m else None


def countries_in(text):
    t = str(text or "").lower()
    return [c for c, keys in COUNTRIES.items() if any(k in t for k in keys)]


def rows_of(book, name):
    try:
        return book.worksheet(name).get_all_records()
    except Exception as e:  # missing tab: skip it
        print(f"  {name}: {e}")
        return []


def yt_id(url):
    m = re.search(r"(?:v=|shorts/|youtu\.be/)([\w-]{11})", str(url))
    return m.group(1) if m else None


def collect(book, yt_limit=160):
    items = []
    for r in rows_of(book, "Candidates"):
        name = str(r.get("Product", "")).strip()
        if not name or not r.get("Status"):
            continue
        note = " ".join(str(r.get(k, "")) for k in ("TikTok Signal", "Meta Longevity", "IG Note", "FB Note", "Saudi Note"))
        items.append({"type": "Candidate", "title": name, "url": r.get("Link", ""),
                      "countries": countries_in(note + " " + str(r.get("Link", ""))) or ["GCC"],
                      "source": r.get("Source", ""), "status": r.get("Status", ""),
                      "price": price_aed(r.get("Market Price (AED)")), "price_label": f"AED {r.get('Market Price (AED)')}" if r.get("Market Price (AED)") else "",
                      "weight": num(r.get("Est. Weight (g)")), "signals": num(r.get("Confirmations")),
                      "trend": r.get("Trends Shape", ""), "note": note.strip()[:240], "date": str(r.get("Date Added", ""))})
    for r in rows_of(book, "Marketplace Signals"):
        items.append({"type": "Amazon", "title": r.get("Product / Keyword", ""), "url": r.get("URL", ""),
                      "countries": [r.get("Country", "")], "source": r.get("Platform", ""),
                      "category": r.get("Category / Query", ""), "rank": num(r.get("Rank")),
                      "price": price_aed(r.get("Price")), "price_label": str(r.get("Price", "")),
                      "reviews": num(re.sub(r"[^\d]", "", str(r.get("Rating / Reviews", ""))) or None),
                      "movement": r.get("Movement", ""), "note": r.get("Note", ""), "date": str(r.get("Scan Date", ""))})
    for r in rows_of(book, "GCC Ad Signals"):
        items.append({"type": "Meta ad", "title": r.get("Product", ""), "url": r.get("URL", ""),
                      "countries": [r.get("Country", "")], "source": r.get("Advertiser", ""),
                      "keyword": r.get("Keyword / Filter", ""), "days": num(r.get("Days Running")),
                      "price": price_aed(r.get("Product", "")) if re.search(r"(AED|SAR|OMR|QAR|KWD)", str(r.get("Product", ""))) else None,
                      "note": r.get("Note", ""), "date": str(r.get("Scan Date", ""))})
    best = {}
    for r in rows_of(book, "YouTube GCC"):
        if str(r.get("Signal Type", "")).lower().startswith("trending"):
            continue  # general trending charts are mostly entertainment, not products
        vid = yt_id(r.get("URL"))
        v = num(r.get("Views")) or 0
        if not vid:
            continue
        cur = best.get(vid)
        if cur is None or v > cur["views"]:
            best[vid] = {"type": "YouTube", "title": r.get("Video Title", ""), "url": r.get("URL", ""),
                         "countries": [r.get("Country", "")], "source": r.get("Channel", ""),
                         "query": r.get("Query / Chart", ""), "views": v, "likes": num(r.get("Likes")),
                         "comments": num(r.get("Comments")), "published": str(r.get("Published", "")),
                         "date": str(r.get("Scan Date", "")), "yt": vid}
        elif r.get("Country") and r.get("Country") not in cur["countries"]:
            cur["countries"].append(r.get("Country"))
    items += sorted(best.values(), key=lambda x: -x["views"])[:yt_limit]
    items += video_products(rows_of(book, "YouTube Products"))
    for i, it in enumerate(items):
        it["id"] = f"{it['type'][0].lower()}{i}"
    return items


GENERIC = re.compile(r"^\(|^(amazon|shop|aliexpress|temu|link|links|india|usa|uk|argentina|buy|here|my |check it|link en bio)\b|"
                     r"international|consultas|storefront|#shorts|\*\*$", re.I)


def _resolve(link):
    """Follow short links (amzn.to, a.co) without opening the product page; return the final URL."""
    url = link
    for _ in range(5):
        try:
            r = requests.head(url, headers=UA, timeout=15, allow_redirects=False)
        except requests.RequestException:
            return url
        nxt = r.headers.get("Location")
        if r.status_code not in (301, 302, 303, 307, 308) or not nxt:
            return url
        url = requests.compat.urljoin(url, nxt)
    return url


def _slug_name(url):
    m = re.search(r"amazon\.[a-z.]+/([^/?]+)/(?:dp|gp/product)/", url)
    if not m or m.group(1) in ("dp", "gp"):
        return None
    return re.sub(r"[-_]+", " ", requests.utils.unquote(m.group(1))).strip()[:90]


def video_products(rows):
    """Products named in product-video descriptions (sheet tab "YouTube Products")."""
    out, seen = [], set()
    for r in rows:
        name, link = str(r.get("Product (from description)", "")).strip(), str(r.get("Shopping link", "")).strip()
        name = re.sub(r"^[^\w(]+", "", name).strip(" :-")
        if not link and (not name or name.startswith("(")):
            continue
        final = _resolve(link) if re.search(r"amzn\.to|a\.co/|amzn\.eu", link) else link
        if GENERIC.search(name) or len(name) < 3 or name.lower() in str(r.get("Video Title", "")).lower():
            name = _slug_name(final) or ""
        if not name:
            continue  # a shop's front page or a link we can't name: not a product
        key = (name.lower(), final.split("?")[0])
        if key in seen:
            continue
        seen.add(key)
        vid = yt_id(r.get("Video"))
        out.append({"type": "Video product", "title": name, "url": final or r.get("Video", ""),
                    "countries": [c.strip() for c in str(r.get("Countries", "")).split(",") if c.strip()],
                    "source": f'{r.get("Channel", "")} video: {str(r.get("Video Title", ""))[:70]}',
                    "views": num(r.get("Views")), "video": r.get("Video", ""), "yt_fallback": vid,
                    "date": str(r.get("Scan Date", ""))[:10]})
    return out


def _amazon_image(url):
    html = requests.get(url, headers=UA, timeout=25).text
    for pat in (r'"hiRes":"(https://[^"]+)"', r'data-old-hires="(https://[^"]+)"',
                r'"large":"(https://m\.media-amazon\.com[^"]+)"', r'<meta property="og:image" content="([^"]+)"',
                r'id="landingImage"[^>]+src="(https://[^"]+)"'):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    if "captcha" in html.lower():
        raise RuntimeError("Amazon captcha")
    return None


_AMAP = None


def _amazon_map():
    """ASIN -> picture id saved from product pages (dashboard/amazon_images.yaml)."""
    global _AMAP
    if _AMAP is None:
        import yaml
        f = Path(__file__).resolve().parent.parent / "dashboard" / "amazon_images.yaml"
        _AMAP = {str(k): str(v) for k, v in (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).items()} if f.exists() else {}
    return _AMAP


def _og_image(url):
    html = requests.get(url, headers=UA, timeout=20).text
    m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html) or \
        re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', html)
    return m.group(1).replace("&amp;", "&") if m else None


_CMAP = None


def _candidate_ref(title):
    """Reference picture for a candidate with no product link (dashboard/candidate_images.yaml)."""
    global _CMAP
    if _CMAP is None:
        import yaml
        found = {}  # fill a local dict first: worker threads must never see a half-filled map
        for name in ("candidate_images.yaml", "meta_images.yaml", "marketplace_images.yaml"):
            f = Path(__file__).resolve().parent.parent / "dashboard" / name
            if f.exists():
                found.update(yaml.safe_load(f.read_text(encoding="utf-8")) or {})
        _CMAP = found
    return _CMAP.get(title)


def image_source(it):
    if it.get("type") == "Video product":
        src = None
        if "amazon." in str(it.get("url", "")):
            try:
                src = image_source({"url": it["url"]})
            except Exception:
                src = None
        return src or (f"https://i.ytimg.com/vi/{it['yt_fallback']}/hqdefault.jpg" if it.get("yt_fallback") else None)
    if it.get("yt"):
        return f"https://i.ytimg.com/vi/{it['yt']}/hqdefault.jpg"
    url = str(it.get("url", ""))
    if "amazon." in url:
        m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
        known = _amazon_map().get(m.group(1)) if m else None
        if known:
            return "https://m.media-amazon.com/images/I/" + known
        if m:  # Amazon's ASIN image endpoint: no product page, so no captcha
            for host in ("m.media-amazon.com", "images-na.ssl-images-amazon.com"):
                src = f"https://{host}/images/P/{m.group(1)}.01._SCLZZZZZZZ_.jpg"
                r = requests.get(src, headers=UA, timeout=20)
                if r.ok and len(r.content) > 2000:
                    return src
        return _amazon_image(url)
    if "youtube.com" in url or "youtu.be" in url:
        vid = yt_id(url)
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None
    if re.search(r"(tiktok|instagram|pinterest|noon)\.com", url):
        return _og_image(url)  # product posts/pages only; blog links would give misleading pictures
    return None


def save_image(src, out_dir, size=360):
    from PIL import Image
    data = requests.get(src, headers=UA, timeout=25).content
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if im.width < 40 or im.height < 40:
        raise RuntimeError("placeholder image")
    im.thumbnail((size, size))
    name = hashlib.sha1(src.encode()).hexdigest()[:16] + ".jpg"
    im.save(out_dir / name, "JPEG", quality=78, optimize=True)
    return name


def run(book, out="dashboard"):
    out = Path(out)
    img_dir = out / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    items = collect(book)
    print(f"{len(items)} items")
    cache = {}

    def work(it):
        url = it.get("yt") or it.get("url")
        if not url:
            return
        try:
            if url not in cache:
                src = image_source(it)
                cache[url] = save_image(src, img_dir) if src else None
                if "amazon." in str(it.get("url")):
                    time.sleep(1.5)
            it["img"] = cache[url]
        except Exception as e:
            it["img"] = None
            it["img_error"] = str(e)[:80]

    def work_ref(it):
        if it["type"] not in ("Candidate", "Meta ad", "Amazon") or it.get("img"):
            return
        ref = _candidate_ref(it["title"])
        if not ref:
            return
        try:
            it["img"] = save_image("https://m.media-amazon.com/images/I/" + ref["img"], img_dir)
            it["ref"] = ref["asin"] not in str(it.get("url", ""))  # same ASIN = the exact product
            it["ref_url"] = "https://www.amazon.ae/dp/" + ref["asin"]
        except Exception as e:
            it["img_error"] = "reference: " + str(e)[:60]

    with ThreadPoolExecutor(3) as ex:
        list(ex.map(work, items))
    _candidate_ref("")  # load the reference map before the threads start
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(work_ref, items))
    got = sum(1 for i in items if i.get("img"))
    print(f"pictures: {got}/{len(items)}")
    for t in ("Candidate", "Amazon", "Meta ad", "YouTube", "Video product"):
        sub = [i for i in items if i["type"] == t]
        print(f"  {t}: {sum(1 for i in sub if i.get('img'))}/{len(sub)} pictures;",
              "; ".join(sorted({i.get('img_error', '') for i in sub if i.get('img_error')}))[:200])
    (out / "data.json").write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    return items
