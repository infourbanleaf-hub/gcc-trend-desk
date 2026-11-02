"""One-off check: which TikTok Creative Center pages/endpoints return Gulf data without a login."""
import json, re, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
tests = {
 "hashtag page SA": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en?region=SA&period=7",
 "products page SA": "https://ads.tiktok.com/business/creativecenter/top-products/pc/en?region=SA",
 "topads page SA": "https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en?region=SA&period=30",
 "api hashtag SA": "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list?page=1&limit=20&period=7&country_code=SA&sort_by=popular",
 "api topads SA": "https://ads.tiktok.com/creative_radar_api/v1/top_ads/v2/list?period=30&page=1&limit=20&order_by=for_you&country_code=SA",
}
for name, url in tests.items():
    try:
        r = requests.get(url, headers=UA, timeout=30)
        t = r.text
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
        info = f"HTTP {r.status_code}, {len(t)} bytes"
        if nd:
            d = nd.group(1)
            tags = re.findall(r'"hashtag_name":"([^"]+)"', d)[:12]
            prods = re.findall(r'"(?:product_name|first_ecom_category|ecom_name)":"([^"]+)"', d)[:12]
            info += f"; NEXT_DATA {len(d)} bytes; hashtags={tags}; products={prods}"
        elif t.lstrip().startswith("{"):
            info += "; json=" + t[:300].replace("\n", " ")
        else:
            info += "; no embedded data"
    except Exception as e:
        info = "ERROR " + str(e)[:200]
    print(f"::notice title={name}::{info[:900]}")
