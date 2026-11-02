"""Amazon.ae / Amazon.sa best sellers + new releases, and Google Trends per Gulf country, through Apify.

Replaces the browser-read Amazon pages of the Monday PC scan with structured data (exact rank, price,
stars, review count, ASIN, picture) that does not depend on the PC being on. Google Trends gives
12 months of weekly search interest per term and country, read by Apify's own Google Trends actor.
Each run is capped in cost (MAX_USD) so a mistake can never use more than a few cents/dollars.
"""
from datetime import datetime, timedelta, timezone

import requests

API = "https://api.apify.com/v2"
GULF = timezone(timedelta(hours=4))
AMAZON_ACTOR = "junglee~amazon-bestsellers"
TRENDS_ACTOR = "apify~google-trends-scraper"
MAX_USD = 2.0

MARKET_HEADERS = ["Scan Date", "Country", "Platform", "Category / Query", "Product / Keyword", "Rank", "Price",
                  "Rating / Reviews", "Movement", "URL", "Note"]
TRENDS_HEADERS = ["Week of", "Country", "Term", "Latest full week (0-100)", "12-month average", "Last 4 weeks vs 4 before (%)",
                  "Peak week", "Trend", "Rising related searches"]
GEO = {"AE": "UAE", "SA": "Saudi Arabia", "KW": "Kuwait", "QA": "Qatar", "OM": "Oman"}


def _run(token, actor, body, wait=290, cap=None):
    r = requests.post(f"{API}/acts/{actor}/runs", params={"token": token, "waitForFinish": wait, "maxTotalChargeUsd": cap or MAX_USD},
                      json=body, timeout=wait + 40)
    r.raise_for_status()
    run = r.json()["data"]
    items = requests.get(f"{API}/datasets/{run['defaultDatasetId']}/items", params={"token": token, "clean": 1},
                         timeout=90).json()
    return run, items


def amazon(token, urls, per_url=30, previous=None, log=print):
    """urls: {url: (country, platform, category)}. previous: {asin_url: last rank} for Movement."""
    run, items = _run(token, AMAZON_ACTOR, {"categoryUrls": [{"url": u} for u in urls], "maxItemsPerStartUrl": per_url,
                                            "depthOfCrawl": 1, "language": "en"})
    log(f"  Amazon: {len(items)} products, run {run['status']}, cost USD {run.get('usageTotalUsd')}")
    stamp = datetime.now(timezone.utc).astimezone(GULF).strftime("%d/%m/%Y")
    rows, previous = [], previous or {}
    for it in items:
        src = (it.get("input") or {}).get("url") if isinstance(it.get("input"), dict) else it.get("input")
        country, platform, cat = urls.get(src) or next((v for k, v in urls.items() if str(src or "").startswith(k)), ("", "", ""))
        if not country:  # fall back to the domain
            country = "UAE" if "amazon.ae" in str(it.get("url")) else "Saudi Arabia" if "amazon.sa" in str(it.get("url")) else ""
            platform = "Amazon.ae Best Sellers" if country == "UAE" else "Amazon.sa Best Sellers"
            cat = it.get("categoryName", "")
        asin = it.get("asin", "")
        dom = "amazon.ae" if country == "UAE" else "amazon.sa"
        url = f"https://www.{dom}/dp/{asin}" if asin else it.get("url", "")
        rank = it.get("position")
        was = previous.get(url)
        if "New Releases" in platform:
            move = "New release"
        elif was is None:
            move = "New in top list"
        elif rank is not None and was != rank:
            move = f"Up from #{was}" if rank < was else f"Down from #{was}"
        else:
            move = "Same rank"
        price = it.get("price") or {}
        price_s = f"{price.get('currency', '')} {price.get('value')}".strip() if price.get("value") is not None else ""
        stars, revs = it.get("stars"), it.get("reviewsCount")
        rr = f"{revs:,} reviews" if revs else ""  # same format as before: the export reads the digits
        img = str(it.get("thumbnailUrl", ""))
        img_id = img.split("/images/I/")[1].split(".")[0] if "/images/I/" in img else ""
        rows.append([stamp, country, platform, cat or it.get("categoryName", ""), " ".join(str(it.get("name", "")).split())[:200],
                     rank, price_s, rr, move, url,
                     " ".join(x for x in (f"img:{img_id}" if img_id else "", f"{stars} stars" if stars else "", "(Apify)") if x)])
    return rows, run


def trends(token, terms, geos=("AE", "SA", "KW", "QA", "OM"), log=print):
    """One run per country; each term is its own 0-100 series (not compared with the others)."""
    stamp = datetime.now(timezone.utc).astimezone(GULF).strftime("%Y-%m-%d")
    rows = []
    for geo in geos:
        try:
            run, items = _run(token, TRENDS_ACTOR, {"searchTerms": terms, "geo": geo, "isMultiple": False,
                                                    "maxItems": len(terms), "skipDebugScreen": True}, cap=0.15)
        except Exception as e:
            log(f"::warning title=Trends {geo}::{str(e)[:150]}")
            continue
        log(f"  Trends {geo}: {len(items)} terms, run {run['status']}, cost USD {run.get('usageTotalUsd')}")
        for it in items:
            tl = [p for p in (it.get("interestOverTime_timelineData") or []) if not p.get("isPartial")]
            vals = [(p.get("formattedAxisTime") or p.get("formattedTime"), (p.get("value") or [None])[0]) for p in tl]
            vals = [(d, v) for d, v in vals if isinstance(v, (int, float))]
            if not vals:
                rows.append([stamp, GEO[geo], it.get("searchTerm") or it.get("inputUrlOrTerm"), "", "", "", "", "Too little search data", ""])
                continue
            series = [v for _, v in vals]
            avg = round(sum(series) / len(series), 1)
            last4, prev4 = series[-4:], series[-8:-4]
            chg = round((sum(last4) - sum(prev4)) / sum(prev4) * 100) if prev4 and sum(prev4) else ""
            peak = max(vals, key=lambda x: x[1])[0]
            trend = ("Rising" if chg != "" and chg >= 15 else "Falling" if chg != "" and chg <= -15 else "Flat") if avg >= 5 else "Too little search data"
            rising = [q.get("query") for q in (it.get("relatedQueries_rising") or []) if isinstance(q, dict)][:3]
            rows.append([stamp, GEO[geo], it.get("searchTerm") or it.get("inputUrlOrTerm"), series[-1], avg, chg, peak, trend,
                         ", ".join(r for r in rising if r)])
    return rows


def usage(token):
    """This billing period's Apify spend, broken down by actor where Apify reports it."""
    me = requests.get(f"{API}/users/me/limits", params={"token": token}, timeout=30).json().get("data", {})
    cur, lim = me.get("current", {}), me.get("limits", {})
    runs = requests.get(f"{API}/actor-runs", params={"token": token, "limit": 50, "desc": 1}, timeout=30).json().get("data", {}).get("items", [])
    by = {}
    for r in runs:
        by[r.get("actId", "?")] = by.get(r.get("actId", "?"), 0) + (r.get("usageTotalUsd") or 0)
    acts = {}
    for aid in by:
        try:
            a = requests.get(f"{API}/acts/{aid}", params={"token": token}, timeout=30).json().get("data", {})
            acts[aid] = f"{a.get('username')}/{a.get('name')}"
        except Exception:
            acts[aid] = aid
    return (f"used USD {cur.get('monthlyUsageUsd')} of {lim.get('maxMonthlyUsageUsd')}; period {me.get('monthlyUsageCycle', {})}; "
            + "; ".join(f"{acts[k]} USD {round(v, 3)}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])))
