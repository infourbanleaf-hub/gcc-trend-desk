"""One-off: Top Ads fields and region list."""
import json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(locale="en-US", viewport={"width": 1366, "height": 900}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
    for region in ["AE", "SA", "KW", "QA", "OM"]:
        got = {}
        page = ctx.new_page()
        def on_resp(r, got=got):
            if "creative_radar_api/v1/top_ads/v2/" in r.url:
                try: got[r.url.split("?")[0].rsplit("/", 1)[1] + "|" + r.url[-60:]] = r.json()
                except Exception: pass
        page.on("response", on_resp)
        try:
            page.goto(f"https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en?region={region}&period=30", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(9000)
        except Exception as e:
            print(f"::warning title={region}::{str(e)[:100]}")
        lists = [v for k, v in got.items() if k.startswith("list")]
        filt = [v for k, v in got.items() if k.startswith("filters")]
        if lists:
            d = lists[0].get("data", {}); m = d.get("materials", [])
            print(f"::notice title={region} list::n={len(m)} pagination={json.dumps(d.get('pagination'))} keys={list(m[0].keys()) if m else []}")
            if region == "SA" and m:
                print("::notice title=SA item::" + json.dumps(m[0], ensure_ascii=False)[:900])
        else:
            print(f"::notice title={region} list::none")
        if filt and region == "SA":
            print("::notice title=filters::" + json.dumps(filt[0], ensure_ascii=False)[:900])
        page.close()
    b.close()
