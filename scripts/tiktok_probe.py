"""One-off check: load TikTok Creative Center pages in a headless browser (from a US server) and capture the
data the page fetches for itself. No login, no clicks beyond page load and scroll."""
import json
from playwright.sync_api import sync_playwright

PAGES = {
 "hashtags SA": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en?region=SA&period=7",
 "hashtags AE": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en?region=AE&period=7",
 "products SA": "https://ads.tiktok.com/business/creativecenter/top-products/pc/en?region=SA",
 "topads SA": "https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en?region=SA&period=30",
 "keywords SA": "https://ads.tiktok.com/business/creativecenter/keyword-insights/pc/en?region=SA",
}
with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(locale="en-US", viewport={"width": 1366, "height": 900}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
    for name, url in PAGES.items():
        got = []
        page = ctx.new_page()
        def on_resp(r, got=got):
            if "creative_radar_api" in r.url:
                try:
                    j = r.json()
                except Exception:
                    j = {}
                got.append((r.url.split("?")[0].split("creative_radar_api")[1], j))
        page.on("response", on_resp)
        hosts = set()
        page.on("request", lambda rq, hosts=hosts: hosts.add(rq.url.split("/")[2]))
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.mouse.wheel(0, 3000); page.wait_for_timeout(4000)
        except Exception as e:
            print(f"::warning title={name}::load error {str(e)[:150]}")
        summ = []
        for path, j in got:
            d = j.get("data") or {}
            lst = d.get("list") or d.get("materials") or d.get("keyword_list") or []
            names = []
            for it in (lst if isinstance(lst, list) else [])[:8]:
                names.append(str(it.get("hashtag_name") or it.get("url_title") or it.get("ad_title") or it.get("keyword")
                                 or it.get("first_ecom_category", {}).get("value") if isinstance(it, dict) else it)[:40])
            summ.append(f"{path} code={j.get('code')} n={len(lst) if isinstance(lst, list) else '?'} {names}")
        try:
            text = f"url={page.url[:90]} title={page.title()[:60]} html={len(page.content())} " + page.inner_text("body")[:200].replace("\n", " | ")
        except Exception as e:
            text = "text error " + str(e)[:80]
        print(f"::notice title={name}::" + (" ;; ".join(summ)[:800] if summ else "no API data captured") + " || " + text[:300] + " || hosts=" + ",".join(sorted(hosts))[:250])
        page.close()
    b.close()
