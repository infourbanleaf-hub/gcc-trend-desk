"""Offline tests: fake Graph API replies, no network, no Google account."""
from datetime import datetime, timezone

import pytest

from trenddesk import audience, instagram
from trenddesk.graph import GraphError

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


class FakeGraph:
    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def get(self, path, **params):
        self.calls.append((path, params))
        for key, reply in self.replies.items():
            if path == key or (callable(key) and key(path, params)):
                if isinstance(reply, Exception):
                    raise reply
                return reply
        raise GraphError(f"unexpected call {path}")

    js = staticmethod(lambda o: str(o))


POST = {"id": "1", "permalink": "https://www.instagram.com/p/AAA/", "timestamp": "2026-10-20T05:00:00+0000",
        "like_count": 400, "comments_count": 12, "media_type": "VIDEO", "caption": "منتج رائع\nfor kitchen"}


def test_pulse_collects_top_and_recent_and_skips_missing_hashtags():
    g = FakeGraph({"ig_hashtag_search": {"data": [{"id": "h1"}]},
                   "h1/top_media": {"data": [POST]}, "h1/recent_media": {"data": [dict(POST, like_count=None)]}})
    posts = instagram.collect_pulse(g, "u1", {"UAE": ["dubaishopping"]}, log=lambda *_: None)
    assert [p["feed"] for p in posts] == ["Top", "Recent"]
    assert posts[1]["likes"] == ""  # hidden like counts stay blank, never 0
    assert posts[0]["caption"] == "منتج رائع for kitchen"


def test_hashtag_budget_enforced():
    with pytest.raises(ValueError):
        instagram.hashtag_budget({"UAE": [f"t{i}" for i in range(29)]})


def test_merge_tracks_growth_and_drops_old_posts():
    first = instagram.collect_pulse(FakeGraph({"ig_hashtag_search": {"data": [{"id": "h1"}]},
                                               "h1/top_media": {"data": [POST]}, "h1/recent_media": {"data": []}}),
                                    "u1", {"UAE": ["x"]}, log=lambda *_: None)
    rows = instagram.merge_pulse([], first, NOW)
    existing = [dict(zip(instagram.PULSE_HEADERS, r)) for r in rows]
    old = dict(existing[0], Link="https://old", **{"Posted (Gulf time)": "2026-09-01 10:00"})
    later = [dict(first[0], likes=1000)]
    rows2 = instagram.merge_pulse(existing + [old], later, NOW)
    assert len(rows2) == 1  # the September post is pruned
    r = dict(zip(instagram.PULSE_HEADERS, rows2[0]))
    assert r["Likes when first seen"] == 400 and r["Likes now"] == 1000 and r["Likes gained"] == 600
    assert r["Likes per hour since posted"] == 250.0  # 1000 likes over 4 hours


def test_shop_rows_follower_change_and_ratio():
    shops = [{"username": "shop.ae", "country": "UAE", "followers": 5200, "posts": 80,
              "media": [dict(POST, like_count=300), dict(POST, permalink="https://b", like_count=100)]}]
    snap, posts = instagram.shop_rows(shops, {"shop.ae": "5,000"}, NOW)
    assert snap[0][4] == 200 and snap[0][6] == 200.0
    assert posts[0][0] == POST["permalink"] and posts[0][6] == 1.5


def test_audience_matches_interest_and_reports_change():
    g = FakeGraph({"search": {"data": [{"id": "6003", "name": "Sunglasses"}]},
                   (lambda p, _: p.endswith("/delivery_estimate")):
                       {"data": [{"estimate_mau_lower_bound": 900000, "estimate_mau_upper_bound": 1100000}]}})
    rows = audience.collect(g, "123", {"UAE": "AE"}, ["Sunglasses"], {("UAE", "Sunglasses"): 1000000.0}, NOW,
                            log=lambda *_: None)
    assert rows == [["2026-10-20", "UAE", "Sunglasses", "Sunglasses", "6003", 900000, 1100000, 100000.0]]
    path, params = g.calls[-1]
    assert path == "act_123/delivery_estimate" and params["optimization_goal"] == "REACH"


def test_api_errors_are_logged_not_fatal():
    g = FakeGraph({"ig_hashtag_search": GraphError("OAuthException 190 token expired")})
    seen = []
    assert instagram.collect_pulse(g, "u1", {"UAE": ["x"]}, log=seen.append) == []
    assert "token expired" in seen[0]
