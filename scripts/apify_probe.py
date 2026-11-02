"""One-off: small real runs of the two actors, report cost, item count and fields."""
import json, os, requests, collections
T = os.environ["APIFY_TOKEN"]; A = "https://api.apify.com/v2"
def run(actor, body):
    r = requests.post(f"{A}/acts/{actor}/runs", params={"token": T, "waitForFinish": 280}, json=body, timeout=320).json()["data"]
    items = requests.get(f"{A}/datasets/{r['defaultDatasetId']}/items", params={"token": T, "clean": 1}, timeout=60).json()
    return r, items
r, items = run("junglee~amazon-bestsellers", {"categoryUrls": [{"url": "https://www.amazon.ae/gp/bestsellers/fashion"}, {"url": "https://www.amazon.sa/gp/bestsellers/home"}], "maxItemsPerStartUrl": 30, "depthOfCrawl": 1, "language": "en"})
print(f"::notice title=Amazon run::status {r['status']} cost USD {r.get('usageTotalUsd')} charged {json.dumps(r.get('chargedEventCounts'))} items {len(items)}")
if items:
    print("::notice title=Amazon fields::" + ", ".join(list(items[0].keys())[:30]))
    print("::notice title=Amazon sample::" + json.dumps({k: items[0].get(k) for k in list(items[0].keys())[:14]}, ensure_ascii=False)[:700])
    print("::notice title=Amazon domains::" + json.dumps(collections.Counter(str(i.get('url', ''))[:22] for i in items)))
r, items = run("apify~google-trends-scraper", {"searchTerms": ["hijab", "abaya", "عباية"], "geo": "SA", "isMultiple": False, "maxItems": 3, "skipDebugScreen": True})
print(f"::notice title=Trends run::status {r['status']} cost USD {r.get('usageTotalUsd')} charged {json.dumps(r.get('chargedEventCounts'))} items {len(items)}")
if items:
    it = items[0]
    print("::notice title=Trends fields::" + ", ".join(it.keys()))
    tl = it.get("interestOverTime_timelineData") or it.get("interestOverTime") or []
    print("::notice title=Trends sample::" + str(it.get("searchTerm") or it.get("inputUrlOrTerm")) + " points " + str(len(tl)) + " " + json.dumps(tl[-3:] if isinstance(tl, list) else tl, ensure_ascii=False)[:500])
