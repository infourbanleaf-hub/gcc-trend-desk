"""One-off: (a) TikTok Top Ads filters + industry-filtered lists, (b) Snapchat Trends reachability."""
import json
from playwright.sync_api import sync_playwright
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(locale="en-US", viewport={"width": 1366, "height": 900}, user_agent=UA)
    for q in ["industry=22000000000", "industry=label_22000000000", "industry=22102000000", "industry=14000000000"]:
        got, reqs = [], []
        pg = ctx.new_page()
        pg.on("request", lambda r, reqs=reqs: reqs.append(r.url) if "top_ads/v2/list" in r.url else None)
        pg.on("response", lambda r, got=got: got.append(r) if "top_ads/v2/list" in r.url or "top_ads/v2/filters" in r.url else None)
        pg.goto(f"https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en?region=SA&period=30&{q}", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(9000)
        out = []
        for r in got:
            try: j = r.json()
            except Exception: continue
            if "filters" in r.url and q.endswith("22000000000"):
                ind = (j.get("data") or {}).get("industry") or []
                print("::notice title=industry filter::" + json.dumps(ind[:3], ensure_ascii=False)[:900])
            if "list" in r.url:
                m = (j.get("data") or {}).get("materials") or []
                out.append(f"n={len(m)} inds={sorted({x.get('industry_key') for x in m})[:6]}")
        print(f"::notice title={q}::list urls={[u.split('?')[1][:160] for u in reqs][:2]} || {out}")
        pg.close()
    # Snapchat Trends
    pg = ctx.new_page(); hits = []
    pg.on("response", lambda r: hits.append(r.url[:120]) if "trends" in r.url and r.request.resource_type in ("xhr", "fetch") else None)
    try:
        pg.goto("https://trends.snapchat.com/", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(8000)
        print("::notice title=snapchat::title=" + pg.title()[:60] + " text=" + pg.inner_text("body")[:500].replace("\n", " | ") + " || xhr=" + ",".join(hits[:6]))
    except Exception as e:
        print("::warning title=snapchat::" + str(e)[:200])
    b.close()
