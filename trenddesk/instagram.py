"""Instagram Graph API collectors: hashtag pulse (hourly) and Gulf shop tracking (daily)."""
from datetime import datetime, timedelta, timezone

from .graph import GraphError

GULF = timezone(timedelta(hours=4))  # UAE/Oman time; KSA/Qatar/Kuwait are one hour behind
FMT = "%Y-%m-%d %H:%M"
POST_FIELDS = "id,caption,like_count,comments_count,timestamp,permalink,media_type"

PULSE_HEADERS = ["Link", "Country", "Hashtag", "Feed", "Posted (Gulf time)", "First seen", "Last seen",
                 "Likes when first seen", "Likes now", "Comments now", "Likes gained",
                 "Likes per hour since posted", "Media type", "Caption"]
SHOP_HEADERS = ["Date", "Username", "Country", "Followers", "Follower change vs last check", "Posts",
                "Avg likes (last 12 posts)", "Best recent post likes", "Best recent post"]
SHOP_POST_HEADERS = ["Link", "Username", "Country", "Posted (Gulf time)", "Likes", "Comments",
                     "Likes vs shop average (x)", "Media type", "Caption"]


def _ts(s):
    """Instagram timestamps look like 2026-10-20T09:15:02+0000."""
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def _num(v):
    return v if isinstance(v, (int, float)) else ""


def _clean(text, n=300):
    return " ".join(str(text or "").split())[:n]


def hashtag_budget(hashtags_by_country):
    tags = {t.strip().lstrip("#") for tags in hashtags_by_country.values() for t in tags}
    if len(tags) > 28:
        raise ValueError(f"{len(tags)} hashtags configured; Instagram allows 30 per 7 days. Keep it at 28 or fewer.")
    return tags


def collect_pulse(graph, user_id, hashtags_by_country, log=print):
    hashtag_budget(hashtags_by_country)
    posts = []
    for country, tags in hashtags_by_country.items():
        for tag in tags:
            tag = tag.strip().lstrip("#")
            try:
                found = graph.get("ig_hashtag_search", user_id=user_id, q=tag).get("data", [])
                if not found:
                    log(f"  #{tag}: no such hashtag")
                    continue
                hid = found[0]["id"]
                for feed in ("top_media", "recent_media"):
                    data = graph.get(f"{hid}/{feed}", user_id=user_id, fields=POST_FIELDS, limit=50).get("data", [])
                    for m in data:
                        if not m.get("permalink") or not m.get("timestamp"):
                            continue
                        posts.append({"link": m["permalink"], "country": country, "hashtag": "#" + tag,
                                      "feed": "Top" if feed == "top_media" else "Recent",
                                      "posted": _ts(m["timestamp"]), "likes": _num(m.get("like_count")),
                                      "comments": _num(m.get("comments_count")),
                                      "media_type": m.get("media_type", ""), "caption": _clean(m.get("caption"))})
                log(f"  #{tag}: ok")
            except GraphError as e:
                log(f"  #{tag}: {e}")
    return posts


def merge_pulse(existing, posts, now, keep_days=14):
    """existing: list of dicts keyed by PULSE_HEADERS (from the sheet). Returns rows sorted hottest first."""
    by_link = {r["Link"]: dict(r) for r in existing if r.get("Link")}
    stamp = now.astimezone(GULF).strftime(FMT)
    for p in posts:
        r = by_link.get(p["link"])
        if r is None:
            r = {"Link": p["link"], "Country": p["country"], "Hashtag": p["hashtag"], "Feed": p["feed"],
                 "Posted (Gulf time)": p["posted"].astimezone(GULF).strftime(FMT), "First seen": stamp,
                 "Likes when first seen": p["likes"]}
            by_link[p["link"]] = r
        elif p["feed"] == "Top":
            r["Feed"] = "Top"
        r.update({"Last seen": stamp, "Likes now": p["likes"], "Comments now": p["comments"],
                  "Media type": p["media_type"], "Caption": p["caption"]})
    cutoff = now - timedelta(days=keep_days)
    rows = []
    for r in by_link.values():
        posted = _parse_local(r.get("Posted (Gulf time)"))
        if posted is None or posted < cutoff:
            continue
        first, cur = _as_num(r.get("Likes when first seen")), _as_num(r.get("Likes now"))
        hours = max((now - posted).total_seconds() / 3600, 1)
        r["Likes gained"] = cur - first if first != "" and cur != "" else ""
        r["Likes per hour since posted"] = round(cur / hours, 1) if cur != "" else ""
        rows.append(r)
    rows.sort(key=lambda r: r["Likes per hour since posted"] if r["Likes per hour since posted"] != "" else -1,
              reverse=True)
    return [[r.get(h, "") for h in PULSE_HEADERS] for r in rows]


def _parse_local(v):
    for f in (FMT, "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(str(v), f).replace(tzinfo=GULF)
        except ValueError:
            continue
    return None


def _as_num(v):
    if v in ("", None):
        return ""
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return ""


def collect_shops(graph, user_id, shops, log=print):
    out = []
    for s in shops:
        name = s["username"].lstrip("@")
        fields = (f"business_discovery.username({name})"
                  f"{{username,followers_count,media_count,media.limit(12){{{POST_FIELDS}}}}}")
        try:
            bd = graph.get(user_id, fields=fields)["business_discovery"]
            out.append({"username": bd.get("username", name), "country": s.get("country", ""),
                        "followers": bd.get("followers_count", ""), "posts": bd.get("media_count", ""),
                        "media": bd.get("media", {}).get("data", [])})
            log(f"  @{name}: ok")
        except (GraphError, KeyError) as e:
            log(f"  @{name}: {e}")
    return out


def shop_rows(shops, previous_followers, now):
    """previous_followers: {username: last recorded followers}. Returns (snapshot_rows, post_rows)."""
    date = now.astimezone(GULF).strftime("%Y-%m-%d")
    snap, posts = [], []
    for s in shops:
        media = s["media"]
        likes = [m["like_count"] for m in media if isinstance(m.get("like_count"), (int, float))]
        avg = round(sum(likes) / len(likes), 1) if likes else ""
        best = max(media, key=lambda m: m.get("like_count") or -1) if media else {}
        prev = _as_num(previous_followers.get(s["username"], ""))
        change = s["followers"] - prev if prev != "" and isinstance(s["followers"], (int, float)) else ""
        snap.append([date, s["username"], s["country"], s["followers"], change, s["posts"], avg,
                     _num(best.get("like_count")), best.get("permalink", "")])
        for m in media:
            if not m.get("permalink"):
                continue
            lk = m.get("like_count")
            ratio = round(lk / avg, 2) if isinstance(lk, (int, float)) and avg else ""
            posted = _ts(m["timestamp"]).astimezone(GULF).strftime(FMT) if m.get("timestamp") else ""
            posts.append([m["permalink"], s["username"], s["country"], posted, _num(lk),
                          _num(m.get("comments_count")), ratio, m.get("media_type", ""), _clean(m.get("caption"))])
    posts.sort(key=lambda r: r[6] if r[6] != "" else -1, reverse=True)
    return snap, posts
