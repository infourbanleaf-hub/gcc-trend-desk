"""Command line: python -m trenddesk {check|pulse|shops|audience} [--dry-run]

--dry-run reads from the APIs but prints the rows instead of writing to the sheet.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import apify_tiktok, audience, export, instagram, sheets, tiktok, trade
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


def _configured_tags(ig):
    return {"#" + t.strip().lstrip("#") for tags in ig["hashtags"].values() for t in tags}


def keep_configured(records_, ig):
    """Drop rows from hashtags no longer in config (e.g. the old city tags, which were mostly news and memes)."""
    tags = _configured_tags(ig)
    return [r for r in records_ if str(r.get("Hashtag", "")).strip() in tags]


def run_pulseclean(cfg, dry):
    """No API calls: remove Instagram Pulse rows whose hashtag is no longer configured."""
    ig = cfg["instagram"]
    book = sheets.open_sheet(cfg["sheet_id"])
    ws = sheets.tab(book, "Instagram Pulse", instagram.PULSE_HEADERS)
    old = records(ws)
    kept = keep_configured(old, ig)
    rows = [[r.get(h, "") for h in instagram.PULSE_HEADERS] for r in kept]
    print(f"::notice title=Pulse clean-up::kept {len(kept)} of {len(old)} rows ({len(old) - len(kept)} from old hashtags removed)")
    if not dry:
        sheets.rewrite(ws, instagram.PULSE_HEADERS, rows)


def run_pulse(cfg, dry):
    if os.environ.get("CLEAN_ONLY") == "true":
        return run_pulseclean(cfg, dry)
    g = Graph(env("IG_ACCESS_TOKEN"), cfg["graph_version"])
    ig = cfg["instagram"]
    now = datetime.now(timezone.utc)
    print("Instagram hashtag pulse")
    t0 = time.time()
    posts = instagram.collect_pulse(g, env("IG_USER_ID"), ig["hashtags"])
    t1 = time.time()
    timing = f"API: {g.calls} calls, {g.retries} retries, {g.wait:.0f}s waiting, {t1 - t0:.0f}s total"
    print(timing)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=API timing::{timing}")
    if dry:
        rows = instagram.merge_pulse([], posts, now, ig.get("keep_days", 14))
        print(f"{len(posts)} posts read; top 10:")
        for r in rows[:10]:
            print("  ", r[1], r[2], r[8], "likes", r[11], "/h", r[0])
        return
    book = sheets.open_sheet(cfg["sheet_id"])
    ws = sheets.tab(book, "Instagram Pulse", instagram.PULSE_HEADERS)
    rows = instagram.merge_pulse(keep_configured(records(ws), ig), posts, now, ig.get("keep_days", 14))
    sheets.rewrite(ws, instagram.PULSE_HEADERS, rows)
    timing += f"; sheet: {time.time() - t1:.0f}s"
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=Timing::{timing}")
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
            msg = fn()
            print(f"OK    {label}: {msg}")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::notice title=OK {label}::{msg}")
        except Exception as e:  # report every problem in one go
            ok = False
            print(f"FAIL  {label}: {e}")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::error title=FAIL {label}::{e}")

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


def run_findshops(cfg, dry):
    """Try candidate Instagram usernames (env SHOP_GUESSES, comma-separated) and report the ones that exist."""
    g = Graph(env("IG_ACCESS_TOKEN"), cfg["graph_version"])
    uid = env("IG_USER_ID")
    for path, fields in (("me/permissions", None), ("me", "id,name"), (uid, "username,account_type")):
        try:
            res = g.get(path, fields=fields) if fields else g.get(path)
            if "data" in res:
                res = ", ".join(f"{p.get('permission')}={p.get('status')}" for p in res["data"])
            print(f"::notice title=Diag {path}::{str(res)[:300]}")
        except Exception as e:
            print(f"::warning title=Diag {path}::{str(e)[:300]}")
    found, missed = [], []
    for name in [n.strip().lstrip("@") for n in os.environ.get("SHOP_GUESSES", "").split(",") if n.strip()]:
        try:
            bd = g.get(uid, fields=f"business_discovery.username({name}){{username,name,followers_count,media_count,biography}}")["business_discovery"]
            bio = " ".join(str(bd.get("biography", "")).split())[:70]
            found.append(f"{name} | {bd.get('name','')} | {bd.get('followers_count')} | {bd.get('media_count')} | {bio}")
        except (GraphError, KeyError) as e:
            missed.append(name)
    # GitHub shows at most 10 notices per step: pack results into a few annotations
    for i in range(0, len(found), 6):
        print(f"::notice title=FOUND {i // 6 + 1}::" + " %0A ".join(found[i:i + 6]))
    print(f"::warning title=MISSED::{', '.join(missed)}")


def run_tiktok(cfg, dry):
    """TikTok Top Ads for the 5 Gulf countries (public Creative Center, no login) -> 'TikTok Top Ads' tab."""
    rows, names = tiktok.collect()
    print(f"::notice title=TikTok Top Ads::{len(rows)} ads; " + ", ".join(
        f"{c}: {sum(1 for r in rows if r[1] == c)}" for c in tiktok.REGIONS.values()))
    if dry or not rows:
        for r in rows[:15]:
            print("  ", r[1], r[4], r[6], r[2][:60])
        return
    book = sheets.open_sheet(cfg["sheet_id"])
    ws = sheets.tab(book, "TikTok Top Ads", tiktok.HEADERS)
    have = {(str(r.get("Scan Date")), str(r.get("Ad ID"))) for r in records(ws)}
    new = [r for r in rows if (r[0], r[8]) not in have]
    sheets.append(ws, new)
    sheets.set_status(book, "Q11", f"Last TikTok scan: {rows[0][0]} - {len(new)} ads (Top Ads, 5 countries)")
    print(f"Wrote {len(new)} rows to TikTok Top Ads")


def run_tthashtags(cfg, dry):
    """TikTok videos for Gulf shopping hashtags via Apify -> 'TikTok Videos' + 'TikTok Hashtag Trend' tabs."""
    tags = cfg["tiktok"]["hashtags"]
    now = datetime.now(timezone.utc)
    items = apify_tiktok.fetch(env("APIFY_TOKEN"), tags, cfg["tiktok"].get("videos_per_hashtag", 25))
    vids, trend = apify_tiktok.rows(items, tags, now)
    print(f"::notice title=TikTok hashtags::{len(vids)} videos over {len(trend)} hashtags")
    for t in trend[:10]:
        print(f"::notice title={t[1]}::{t[3]} posted in last 7 days; median views {t[4]}; top {t[6]}")
    if dry or not vids:
        return
    book = sheets.open_sheet(cfg["sheet_id"])
    sheets.append(sheets.tab(book, "TikTok Videos", apify_tiktok.VIDEO_HEADERS), vids)
    sheets.append(sheets.tab(book, "TikTok Hashtag Trend", apify_tiktok.TREND_HEADERS), trend)
    sheets.set_status(book, "Q12", f"Last TikTok hashtag scan: {trend[0][0]} - {len(vids)} videos, {len(trend)} hashtags (Apify)")


def run_trade(cfg, dry):
    tc = cfg["trade"]
    groups = {str(k): v for k, v in tc["hs"].items()}
    print("India exports to GCC (UN Comtrade)")
    values = trade.fetch(list(groups), tc["years"])
    rows = trade.rows(values, groups, tc["years"])
    print(f"::notice title=Trade data::{len(values)} values, {len(rows)} rows, years {sorted({y for (_, _, y) in values})}")
    for r in rows[:12]:
        print(f"::notice title=Top {r[0]} {r[2]}::{r[1][:40]} | {r[3]}: USD {r[4]:,} (prev {r[5]:,}, {r[6]}%)")
    if dry:
        return
    book = sheets.open_sheet(cfg["sheet_id"])
    ws = sheets.tab(book, "India Exports to GCC", trade.TRADE_HEADERS)
    sheets.rewrite(ws, trade.TRADE_HEADERS, rows)
    sheets.set_status(book, "Q10", f"Last trade-data update: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} - {len(rows)} rows (UN Comtrade)")


def run_export(cfg, dry):
    export.run(sheets.open_sheet(cfg["sheet_id"]))


def main():
    p = argparse.ArgumentParser(prog="trenddesk")
    p.add_argument("job", choices=["check", "pulse", "shops", "audience", "export", "findshops", "trade", "tiktok", "tthashtags"])
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    cfg = load_config()
    try:
        {"check": run_check, "pulse": run_pulse, "shops": run_shops, "audience": run_audience, "export": run_export, "findshops": run_findshops, "trade": run_trade, "tiktok": run_tiktok, "tthashtags": run_tthashtags}[a.job](cfg, a.dry_run)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        if os.environ.get("GITHUB_ACTIONS"):
            where = traceback.extract_tb(e.__traceback__)[-1]
            print(f"::error title={a.job} crashed::{type(e).__name__}: {str(e)[:400]} (at {Path(where.filename).name}:{where.lineno})")
        sys.exit(1)


if __name__ == "__main__":
    main()
