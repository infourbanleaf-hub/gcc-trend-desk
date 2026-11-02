"""TikTok Top Ads for the Gulf, from TikTok's public Creative Center (no login).

TikTok is blocked in India, so this runs on GitHub's servers. The Creative Center page signs its own data
requests, so we open it in a headless browser and keep the JSON the page loads for itself
(creative_radar_api/v1/top_ads/v2/list). Each country's list holds TikTok's top-performing auction ads
of the last 30 days; we read the first pages that load without signing in.
"""
import json
from datetime import datetime, timedelta, timezone

GULF = timezone(timedelta(hours=4))
REGIONS = {"AE": "UAE", "SA": "Saudi Arabia", "KW": "Kuwait", "QA": "Qatar", "OM": "Oman"}
PAGE = "https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en?region={code}&period={period}"
DETAIL = "https://ads.tiktok.com/business/creativecenter/topads/{id}/pc/en?countryCode={code}&from=001110&period={period}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0.0.0 Safari/537.36")

HEADERS = ["Scan Date", "Country", "Ad title", "Brand", "Industry", "Objective", "Likes", "CTR (TikTok)",
           "Ad ID", "Link", "Cover image", "Video length (s)"]


def _labels(filters):
    """industry_key -> readable industry name, from the page's own filter list."""
    out = {}

    def walk(items, parent=""):
        for it in items or []:
            key, label = it.get("id") or it.get("value"), it.get("label") or it.get("value") or ""
            name = str(label).replace("label_", "").replace("_", " ").strip()
            if key:
                out[str(key)] = (parent + " > " + name) if parent and name else name
            walk(it.get("sub_industry") or it.get("children"), name)

    data = (filters or {}).get("data") or {}
    walk(data.get("industry"))
    return out


def collect(periods=(7, 30, 180), log=print):
    """Return (rows, industry_names). Without a login TikTok serves one page of 20 ads per list, so each
    country's 7-, 30- and 180-day lists are read to see more ads (duplicates across lists are dropped)."""
    from playwright.sync_api import sync_playwright

    rows, names = [], {}
    stamp = datetime.now(timezone.utc).astimezone(GULF).strftime("%Y-%m-%d")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(locale="en-US", viewport={"width": 1366, "height": 900}, user_agent=UA)
        for code, country in REGIONS.items():
            seen = set()
            for period in periods:
                lists, filters = [], {}
                page = ctx.new_page()

                def on_resp(r, lists=lists, filters=filters):
                    if "creative_radar_api/v1/top_ads/v2/list" in r.url:
                        try:
                            lists.append(r.json())
                        except Exception:
                            pass
                    elif "creative_radar_api/v1/top_ads/v2/filters" in r.url:
                        try:
                            filters.update(r.json())
                        except Exception:
                            pass

                page.on("response", on_resp)
                try:
                    page.goto(PAGE.format(code=code, period=period), wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(9000)
                except Exception as e:
                    log(f"::warning title=TikTok {country} {period}d::{str(e)[:150]}")
                names.update(_labels(filters))
                for js in lists:
                    for m in ((js.get("data") or {}).get("materials") or []):
                        if m.get("id") in seen:
                            continue
                        seen.add(m.get("id"))
                        v = m.get("video_info") or {}
                        rows.append([stamp, country, " ".join(str(m.get("ad_title", "")).split())[:300],
                                     "" if m.get("brand_name") in (None, "Not Mention") else m.get("brand_name"),
                                     str(m.get("industry_key", "")).replace("label_", ""),
                                     str(m.get("objective_key", "")).replace("campaign_objective_", ""),
                                     m.get("like", ""), m.get("ctr", ""), str(m.get("id", "")),
                                     DETAIL.format(id=m.get("id"), code=code, period=period),
                                     v.get("cover", ""), round(v.get("duration") or 0)])
                page.close()
            log(f"  {country}: {len(seen)} ads")
        browser.close()
    return rows, names
