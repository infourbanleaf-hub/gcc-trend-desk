"""One-off: find Apify actors for Amazon best sellers (ae/sa) and Google Trends; print pricing + input schema."""
import json, os, requests
T = os.environ["APIFY_TOKEN"]
A = "https://api.apify.com/v2"
def get(path, **p):
    p["token"] = T
    return requests.get(A + path, params=p, timeout=60).json()
for q in ["amazon bestsellers", "amazon best sellers marketplace", "google trends"]:
    items = (get("/store", search=q, limit=12).get("data") or {}).get("items", [])
    for it in items:
        pr = it.get("currentPricingInfo") or {}
        st = it.get("stats") or {}
        print(f"::notice title={q}::{it.get('username')}/{it.get('name')} | users30d {st.get('totalUsers30Days')} | rating {it.get('actorReviewRating')} | price {pr.get('pricingModel')} {pr.get('pricePerUnitUsd') or pr.get('pricePerEvent') or ''}"[:300])
def schema(actor):
    a = get(f"/acts/{actor.replace('/', '~')}").get("data") or {}
    bid = ((a.get("taggedBuilds") or {}).get("latest") or {}).get("buildId")
    b = get(f"/acts/{actor.replace('/', '~')}/builds/{bid}").get("data") or {} if bid else {}
    sch = b.get("inputSchema")
    sch = json.loads(sch) if isinstance(sch, str) else (sch or {})
    props = sch.get("properties", {})
    out = []
    for k, v in props.items():
        en = v.get("enum") or v.get("enumTitles") or ""
        out.append(f"{k}({v.get('type')}){'='+json.dumps(v.get('prefill') or v.get('default'))[:60] if (v.get('prefill') or v.get('default')) else ''}{' enum:'+','.join(map(str,en))[:160] if en else ''}")
    pr = a.get("pricingInfos") or []
    print(f"::notice title=schema {actor}::price={json.dumps(pr[-1] if pr else {})[:200]} || " + " ; ".join(out)[:700])
for actor in os.environ.get("CHECK", "").split(","):
    if actor.strip():
        try:
            schema(actor.strip())
        except Exception as e:
            print(f"::warning title={actor}::{e}")
