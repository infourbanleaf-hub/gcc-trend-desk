"""Meta Marketing API: how many people per Gulf country Meta can reach for each interest."""
from datetime import datetime

from .graph import GraphError
from .instagram import GULF

AUDIENCE_HEADERS = ["Date", "Country", "Search term", "Meta interest", "Interest ID",
                    "Monthly audience (low)", "Monthly audience (high)", "Change vs last check (high)"]


def match_interest(graph, term):
    data = graph.get("search", type="adinterest", q=term, limit=1).get("data", [])
    return (data[0]["id"], data[0]["name"]) if data else (None, None)


def estimate(graph, ad_account_id, country_code, interest_id):
    spec = {"geo_locations": {"countries": [country_code]},
            "flexible_spec": [{"interests": [{"id": interest_id}]}]}
    d = graph.get(f"act_{ad_account_id}/delivery_estimate", optimization_goal="REACH",
                  targeting_spec=graph.js(spec)).get("data", [{}])[0]
    return d.get("estimate_mau_lower_bound", ""), d.get("estimate_mau_upper_bound", "")


def collect(graph, ad_account_id, countries, terms, previous_high, now: datetime, log=print):
    """previous_high: {(country, term): last high estimate}."""
    date = now.astimezone(GULF).strftime("%Y-%m-%d")
    rows = []
    for term in terms:
        try:
            iid, iname = match_interest(graph, term)
        except GraphError as e:
            log(f"  {term}: {e}")
            continue
        if not iid:
            log(f"  {term}: no matching Meta interest")
            continue
        for country, code in countries.items():
            try:
                low, high = estimate(graph, ad_account_id, code, iid)
            except GraphError as e:
                log(f"  {term} / {country}: {e}")
                continue
            prev = previous_high.get((country, term), "")
            change = high - prev if isinstance(high, (int, float)) and isinstance(prev, (int, float)) else ""
            rows.append([date, country, term, iname, str(iid), low, high, change])
        log(f"  {term} -> {iname}: ok")
    return rows
