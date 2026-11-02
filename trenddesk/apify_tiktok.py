"""TikTok videos for Gulf shopping hashtags, through Apify (apify.com).

TikTok is blocked in India, so nobody in the business opens TikTok: Apify's servers (outside India) read the
public TikTok videos for each hashtag and return views, likes, comments, shares and saves. You only use
apify.com, which works from India. Needs the GitHub secret APIFY_TOKEN.

Actor: clockworks/tiktok-scraper (public videos by hashtag). Apify bills per result; the free plan includes
USD 5 of usage a month, which covers the default settings below (about 14 hashtags x 25 videos a week).
"""
from datetime import datetime, timedelta, timezone

import requests


def _auth(token):
    """Send the key in a header, never in the web address, so it cannot appear in error messages or logs."""
    return {"Authorization": f"Bearer {token}"}

GULF = timezone(timedelta(hours=4))
ACTOR = "clockworks~tiktok-scraper"
VIDEO_HEADERS = ["Scan Date", "Hashtag", "Posted (Gulf time)", "Author", "Author followers", "Views", "Likes",
                 "Comments", "Shares", "Saves", "Caption", "Link", "Cover image"]
TREND_HEADERS = ["Week of", "Hashtag", "Videos read", "Posted in last 7 days", "Median views",
                 "Views, last-7-day videos", "Top video views", "Top video", "Top video caption"]


def _g(d, *keys, default=""):
    for k in keys:
        cur = d
        for part in k.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur not in (None, ""):
            return cur
    return default


def fetch(token, hashtags, per_tag=25, log=print):
    """Run the actor once for all hashtags and return its dataset items."""
    url = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
    body = {"hashtags": hashtags, "resultsPerPage": per_tag, "shouldDownloadVideos": False,
            "shouldDownloadCovers": False, "shouldDownloadSubtitles": False, "shouldDownloadSlideshowImages": False}
    r = requests.post(url, headers=_auth(token), params={"timeout": 290}, json=body, timeout=320)
    if r.status_code >= 400:
        raise RuntimeError(f"Apify HTTP {r.status_code}: {r.text[:300]}")
    items = r.json()
    log(f"  Apify returned {len(items)} videos")
    return items


def rows(items, hashtags, now):
    stamp = now.astimezone(GULF).strftime("%Y-%m-%d")
    wanted = {h.lower().lstrip("#") for h in hashtags}
    vids = []
    for it in items:
        tag = str(_g(it, "input", "searchHashtag.name", "hashtag")).lstrip("#")
        if tag.lower() not in wanted:  # fall back to the first configured hashtag the video carries
            tags = [str(h.get("name", "")).lower() for h in (it.get("hashtags") or []) if isinstance(h, dict)]
            tag = next((h for h in hashtags if h.lower().lstrip("#") in tags), tag)
        posted = _g(it, "createTimeISO")
        try:
            posted_dt = datetime.fromisoformat(str(posted).replace("Z", "+00:00"))
            posted = posted_dt.astimezone(GULF).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            posted_dt = None
        vids.append({"row": [stamp, "#" + tag.lstrip("#"), posted, _g(it, "authorMeta.name", "authorMeta.nickName"),
                             _g(it, "authorMeta.fans"), _g(it, "playCount"), _g(it, "diggCount"),
                             _g(it, "commentCount"), _g(it, "shareCount"), _g(it, "collectCount"),
                             " ".join(str(_g(it, "text")).split())[:300], _g(it, "webVideoUrl"),
                             _g(it, "videoMeta.coverUrl", "videoMeta.originalCoverUrl")],
                     "tag": "#" + tag.lstrip("#"), "posted": posted_dt, "views": _num(_g(it, "playCount"))})
    trend = []
    week_ago = now - timedelta(days=7)
    for tag in sorted({v["tag"] for v in vids}):
        vs = [v for v in vids if v["tag"] == tag]
        recent = [v for v in vs if v["posted"] and v["posted"] >= week_ago]
        views = sorted(v["views"] for v in vs if v["views"] is not None)
        top = max(vs, key=lambda v: v["views"] or 0)
        trend.append([stamp, tag, len(vs), len(recent), views[len(views) // 2] if views else "",
                      sum(v["views"] or 0 for v in recent), top["views"] or "", top["row"][11], top["row"][10][:150]])
    return [v["row"] for v in vids], trend


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
