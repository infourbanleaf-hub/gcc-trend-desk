"""Command line: python -m trenddesk {check|pulse|shops|audience} [--dry-run]

--dry-run reads from the APIs but prints the rows instead of writing to the sheet.
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import audience, instagram, sheets
from .graph import Graph, GraphError

ROOT = Path(__file__).resolve().parent.parent


def load_config():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def env(name):
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"Missing GitHub secret {name}. See SETUP.md.")
    return v


def records(ws):
    try:
        return ws.get_all_records()
    except Exception:
        return []


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return ""


def run_pulse(cfg, dry):
    g = Graph(env("IG_ACCESS_TOKEN"), cfg["graph_version"])
    ig = cfg["instagram"]
    now = datetime.now(timezone.utc)
    print("Instagram hashtag pulse")
    posts = instagram.collect_pulse(g, env("IG_USER_ID"), ig["hashtags"])
    if dry:
        rows = instagram.merge_pulse([], posts, now, ig.get("keep_days", 14))
        print(f"{len(posts)} posts read; top 10:")
        for r in rows[:10]:
            print("  ", r[1], r[2], r[8], "likes", r[11], "/h", r[0])
        return
    book = sheets.open_sheet(cfg["sheet_id"])
    ws = sheets.tab(book, "Instagram Pulse", instagram.PULSE_HEADERS)
    rows = instagram.merge_pulse(records(ws), posts, now, ig.get("keep_days", 14))
    sheets.rewrite(ws, instagram.PULSE_HEADERS, rows)
    stamp = now.astimezone(instagram.GULF).strftime(instagram.FMT)
    sheets.set_status(book, "Q6", f"Last Instagram pulse: {stamp} Gulf time - {len(posts)} posts read, {len(rows)} tracked")
    print(f"Wrote {len(rows)} rows to Instagram Pulse")


def run_shops(cfg, dry):
    shops = cfg["instagram"].get("shops") or []
    if not shops:
        print("No shops listed in config.yaml (instagram.shops) - nothing to do.")
        return
    g = Graph(env("IG_ACCESS_TOKEN"), cfg["graph_version"])
    now = datetime.now(timezone.utc)
    print("Gulf shop tracking")
    found = instagram.collect_shops(g, env("IG_USER_ID"), shops)
    if dry:
        snap, posts = instagram.shop_rows(found, {}, now)
        for r in snap:
            print("  ", r)
        return
    book = sheets.open_sheet(cfg["sheet_id"])
    ws = sheets.tab(book, "Gulf Shops", instagram.SHOP_HEADERS)
    prev = {}
    for r in records(ws):  # later rows overwrite earlier ones = most recent value per shop
        prev[r.get("Username")] = r.get("Followers")
    snap, posts = instagram.shop_rows(found, prev, now)
    sheets.append(ws, snap)
    wp = sheets.tab(book, "Gulf Shop Posts", instagram.SHOP_POST_HEADERS)
    sheets.rewrite(wp, instagram.SHOP_POST_HEADERS, posts)
    sheets.set_status(book, "Q7", f"Last shop check: {now.astimezone(instagram.GULF).strftime(instagram.FMT)} Gulf time - {len(snap)} shops")
    print(f"Wrote {len(snap)} shop rows and {len(posts)} post rows")


def run_audience(cfg, dry):
    g = Graph(env("IG_ACCESS_TOKEN"), cfg["graph_version"])
    ma = cfg["meta_audience"]
    now = datetime.now(timezone.utc)
    print("Meta audience sizes")
    book = None if dry else sheets.open_sheet(cfg["sheet_id"])
    prev = {}
    if book:
        ws = sheets.tab(book, "Audience Size", audience.AUDIENCE_HEADERS)
        for r in records(ws):
            prev[(r.get("Country"), r.get("Search term"))] = num(r.get("Monthly audience (high)"))
    rows = audience.collect(g, env("META_AD_ACCOUNT_ID").replace("act_", ""), ma["countries"], ma["interests"], prev, now)
    if dry:
        for r in rows:
            print("  ", r)
        return
    sheets.append(ws, rows)
    sheets.set_status(book, "Q8", f"Last audience check: {now.astimezone(instagram.GULF).strftime('%Y-%m-%d')} - {len(rows)} rows")
    print(f"Wrote {len(rows)} rows to Audience Size")


def run_check(cfg, dry):
    ok = True

    def report(label, fn):
        nonlocal ok
        try:
            print(f"OK    {label}: {fn()}")
        except Exception as e:  # report every problem in one go
            ok = False
            print(f"FAIL  {label}: {e}")

    def need(name, note=""):
        v = os.environ.get(name, "").strip()
        if not v:
            raise GraphError(f"secret {name} not set{note}")
        return v

    report("Hashtag list", lambda: f"{len(instagram.hashtag_budget(cfg['instagram']['hashtags']))} hashtags (limit 28)")
    graph = lambda: Graph(need("IG_ACCESS_TOKEN"), cfg["graph_version"])
    report("Meta access token", lambda: graph().get("me", fields="id,name")["name"])
    report("Instagram business account",
           lambda: "@" + graph().get(need("IG_USER_ID"), fields="username,followers_count")["username"])
    first_tag = next(t for tags in cfg["instagram"]["hashtags"].values() for t in tags).lstrip("#")
    report("Hashtag search permission (Instagram Public Content Access)", lambda: "#" + first_tag + " found" if graph().get(
        "ig_hashtag_search", user_id=need("IG_USER_ID"), q=first_tag).get("data") else "#" + first_tag + " returned nothing")
    report("Meta ad account", lambda: graph().get(
        "act_" + need("META_AD_ACCOUNT_ID", " (needed only for audience sizes)").replace("act_", ""),
        fields="name,account_status")["name"])
    report("Google Sheet access", lambda: sheets.open_sheet(cfg["sheet_id"]).title)
    print("\nAll checks passed." if ok else "\nFix the FAIL lines above (see SETUP.md), then run this check again.")
    if not ok:
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(prog="trenddesk")
    p.add_argument("job", choices=["check", "pulse", "shops", "audience"])
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    cfg = load_config()
    {"check": run_check, "pulse": run_pulse, "shops": run_shops, "audience": run_audience}[a.job](cfg, a.dry_run)


if __name__ == "__main__":
    main()
