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
        self.http = session or requests  # module-level get: safe to call from several threads
        self.calls = 0
        self.retries = 0
        self.wait = 0.0

    def get(self, path, **params):
        params["access_token"] = self.token
        for attempt in range(3):
            t0 = time.time()
            try:
                r = self.http.get(self.base + path.lstrip("/"), params=params, timeout=60)
            except requests.RequestException as e:  # timeouts, dropped connections
                self.calls += 1
                self.wait += time.time() - t0
                if attempt < 2:
                    self.retries += 1
                    time.sleep(5 * (attempt + 1))
                    continue
                raise GraphError(f"{path}: {type(e).__name__} after 3 tries")
            self.calls += 1
            self.wait += time.time() - t0
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                self.retries += 1
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
