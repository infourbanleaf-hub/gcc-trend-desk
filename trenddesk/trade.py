"""India's exports to the GCC by HS code, from UN Comtrade's free public API.

India reports its trade reliably every year, so India's exports to each Gulf country are used
(the Gulf countries' own import reports are often late or missing in Comtrade).
"""
import time

import requests

API = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
INDIA = 699
GCC = {784: "UAE", 682: "Saudi Arabia", 414: "Kuwait", 634: "Qatar", 512: "Oman"}

TRADE_HEADERS = ["HS code", "Product group", "Country", "Year", "India exports (USD)",
                 "Previous year (USD)", "Change %", "Note"]


def fetch(hs_codes, years, log=print):
    """{(hs, country, year): usd}"""
    out = {}
    for i in range(0, len(hs_codes), 8):
        cmds = ",".join(hs_codes[i:i + 8])
        params = {"reporterCode": INDIA, "partnerCode": ",".join(map(str, GCC)), "flowCode": "X",
                  "period": ",".join(map(str, years)), "cmdCode": cmds, "includeDesc": "true"}
        for attempt in range(4):
            r = requests.get(API, params=params, timeout=60)
            if r.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        for row in r.json().get("data", []) or []:
            if row.get("partner2Code") not in (0, None) or row.get("customsCode") not in ("C00", None):
                continue
            key = (str(row["cmdCode"]), GCC.get(row["partnerCode"], str(row["partnerCode"])), int(row["period"]))
            out[key] = out.get(key, 0) + float(row.get("primaryValue") or 0)
        log(f"  HS {cmds}: ok")
        time.sleep(2)
    return out


def rows(values, groups, years):
    latest = max(y for (_, _, y) in values) if values else max(years)
    res = []
    for hs, name in groups.items():
        for country in GCC.values():
            now = values.get((hs, country, latest))
            prev = values.get((hs, country, latest - 1))
            if now is None and prev is None:
                continue
            chg = round((now - prev) / prev * 100, 1) if now is not None and prev else ""
            note = "growing fast" if chg != "" and chg >= 25 else ("falling" if chg != "" and chg <= -15 else "")
            res.append([hs, name, country, latest, round(now or 0), round(prev or 0), chg, note])
    res.sort(key=lambda r: -r[4])
    return res
