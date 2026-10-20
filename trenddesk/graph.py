"""Minimal client for Meta's Graph API (Instagram Graph API + Marketing API)."""
import json
import time

import requests


class GraphError(RuntimeError):
    pass


class Graph:
    def __init__(self, token, version="v23.0", session=None):
        if not token:
            raise GraphError("Missing access token (GitHub secret IG_ACCESS_TOKEN).")
        self.token = token
        self.base = f"https://graph.facebook.com/{version}/"
        self.http = session or requests.Session()

    def get(self, path, **params):
        params["access_token"] = self.token
        for attempt in range(3):
            r = self.http.get(self.base + path.lstrip("/"), params=params, timeout=30)
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            try:
                body = r.json()
            except ValueError:
                raise GraphError(f"{path}: HTTP {r.status_code}, non-JSON reply")
            if "error" in body:
                e = body["error"]
                raise GraphError(f"{path}: {e.get('type', '')} {e.get('code', '')} {e.get('message', '')}".strip())
            return body
        raise GraphError(f"{path}: gave up after retries")

    @staticmethod
    def js(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
