"""reddit.py — akses Reddit lewat OAuth application-only.

Endpoint JSON tanpa token diblokir (403) dari IP datacenter, termasuk
www.reddit.com/.json dan api.reddit.com. Yang masih boleh: /api/v1/access_token.
Jadi token diambil dulu, lalu semua panggilan lewat oauth.reddit.com.

Butuh app tipe "script" dari https://www.reddit.com/prefs/apps
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

_DEFAULT_UA = "macos:pantau:1.0.0 (by /u/pantau)"
_CFG: dict[str, str] = {"client_id": "", "client_secret": "", "ua": _DEFAULT_UA}
_TOKEN: dict[str, float | str] = {"value": "", "exp": 0.0}


class RedditError(RuntimeError):
    pass


def configure(client_id: str, client_secret: str, ua: str = "") -> None:
    _CFG["client_id"] = client_id or ""
    _CFG["client_secret"] = client_secret or ""
    _CFG["ua"] = ua or _DEFAULT_UA
    _TOKEN["value"] = ""
    _TOKEN["exp"] = 0.0


def configured() -> bool:
    return bool(_CFG["client_id"] and _CFG["client_secret"])


def _post_token() -> str:
    if not configured():
        raise RedditError("client_id / client_secret belum diisi")
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request("https://www.reddit.com/api/v1/access_token",
                                 data=body, method="POST")
    cred = f"{_CFG['client_id']}:{_CFG['client_secret']}".encode()
    req.add_header("Authorization", "Basic " + base64.b64encode(cred).decode())
    req.add_header("User-Agent", _CFG["ua"])
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise RedditError(f"token ditolak ({exc.code}): {detail}") from exc
    token = data.get("access_token")
    if not token:
        raise RedditError(f"token kosong: {data}")
    _TOKEN["value"] = token
    _TOKEN["exp"] = time.time() + float(data.get("expires_in", 3600))
    return token


def _token() -> str:
    value = str(_TOKEN["value"])
    if value and time.time() < float(_TOKEN["exp"]) - 60:
        return value
    return _post_token()


def _get(path: str, params: dict, retries: int = 3) -> dict:
    url = "https://oauth.reddit.com" + path + "?" + urllib.parse.urlencode(params)
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {_token()}")
        req.add_header("User-Agent", _DEFAULT_UA)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 401:
                _TOKEN["value"] = ""
            time.sleep(20 if exc.code == 429 else 2 ** attempt)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 ** attempt)
    raise RedditError(f"gagal ambil {path}: {last}")


def _item(child: dict) -> dict:
    d = child.get("data", {})
    permalink = d.get("permalink", "")
    url = f"https://www.reddit.com{permalink}" if permalink else d.get("url", "")
    body = d.get("selftext") or d.get("url_overridden_by_dest") or ""
    return {
        "url": url,
        "title": d.get("title", ""),
        "snippet": body[:600],
        "published": int(d["created_utc"]) if d.get("created_utc") else None,
    }


def listing(subreddit: str, limit: int = 100, sort: str = "new") -> list[dict]:
    data = _get(f"/r/{subreddit}/{sort}", {"limit": limit, "raw_json": 1})
    return [_item(c) for c in data.get("data", {}).get("children", [])]


def search(query: str, limit: int = 100, time_filter: str = "day",
           sort: str = "new") -> list[dict]:
    data = _get("/search", {"q": query, "sort": sort, "t": time_filter,
                            "limit": limit, "raw_json": 1})
    return [_item(c) for c in data.get("data", {}).get("children", [])]


def check() -> dict:
    """Diagnostik: pastikan kredensial diterima dan endpoint listing bisa dibaca."""
    token = _post_token()
    info = _get("/r/ClaudeAI/about", {"raw_json": 1})
    return {
        "token": token[:8] + "…",
        "subreddit": info.get("data", {}).get("display_name", "?"),
        "subscribers": info.get("data", {}).get("subscribers", 0),
    }