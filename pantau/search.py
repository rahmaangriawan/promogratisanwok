"""search.py — pengambil hasil dari beberapa mesin pencari tanpa API key.

ddg  : html.duckduckgo.com/html (POST) — paling gampang, tanpa key
bing : www.bing.com/search?q=...&format=rss — RSS resmi, stabil
gh   : api.github.com/search/issues — publik, rate-limit ringan
rss  : umpan apa pun (reddit .json, hnrss, forum)

Semua fungsi mengembalikan list[dict] dengan kunci: url, title, snippet.
"""

from __future__ import annotations

import base64
import datetime as _dt
import email.utils
import html
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Iterable

UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
]


def _ua() -> str:
    return random.choice(UA_POOL)


_LAST_HIT: dict[str, float] = {}
_MIN_GAP = {"reddit.com": 20.0, "www.reddit.com": 20.0, "old.reddit.com": 20.0}


def _get(url: str, timeout: int = 25, retries: int = 3,
         data: bytes | None = None, headers: dict | None = None) -> bytes:
    host = urllib.parse.urlsplit(url).hostname or ""
    gap = _MIN_GAP.get(host, 1.0)
    last: Exception | None = None
    for attempt in range(retries):
        wait = gap - (time.monotonic() - _LAST_HIT.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _LAST_HIT[host] = time.monotonic()
        try:
            req = urllib.request.Request(url, data=data)
            req.add_header("User-Agent", _ua())
            req.add_header("Accept-Language", "id-ID,id;q=0.9,en;q=0.8")
            req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            for k, v in (headers or {}).items():
                req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            last = exc
            # reddit memblokir keras kalau dipanggil beruntun: tunggu lebih lama
            wait_s = (12 + attempt * 10) if exc.code == 429 else (2 ** attempt + random.random())
            time.sleep(wait_s)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep((2 ** attempt) + random.random())
    raise RuntimeError(f"gagal ambil {url}: {last}")


def _clean(s: str) -> str:
    s = s.replace("<![CDATA[", " ").replace("]]>", " ")
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def parse_date(raw: str) -> int | None:
    """Ubah pubDate RSS / waktu ISO jadi epoch. None kalau tidak terbaca."""
    if not raw:
        return None
    raw = _clean(raw)
    try:  # RFC 822: Wed, 05 Nov 2026 12:00:00 GMT
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        pass
    try:  # ISO 8601: 2026-11-05T12:00:00Z / +07:00
        iso = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _domain(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


# ---------------------------------------------------------------- duckduckgo
DDG_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'(?:.*?class="result__snippet"[^>]*>(?P<snippet>.*?)</a>)?',
    re.S,
)


def search_ddg(query: str, timeout: int = 20) -> list[dict]:
    body = urllib.parse.urlencode({"q": query, "kl": "id-id"}).encode()
    raw = _get("https://html.duckduckgo.com/html/", timeout=timeout, data=body,
               headers={"Content-Type": "application/x-www-form-urlencoded"})
    page = raw.decode("utf-8", "replace")
    out = []
    for m in DDG_RE.finditer(page):
        href = m.group("url")
        if "uddg=" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = qs.get("uddg", [href])[0]
        if not href.startswith("http"):
            continue
        out.append({
            "url": href,
            "title": _clean(m.group("title") or ""),
            "snippet": _clean(m.group("snippet") or ""),
        })
    return out[:30]


# ---------------------------------------------------------------- bing rss
def search_bing(query: str, timeout: int = 20) -> list[dict]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({
        "q": query, "format": "rss", "setlang": "id", "cc": "ID",
        "filters": 'ex1:"ez1"',   # ez1 = 24 jam terakhir
    })
    raw = _get(url, timeout=timeout).decode("utf-8", "replace")
    return _parse_rss(raw)


# ---------------------------------------------------------------- bing html
BING_BLOCK = re.compile(r'<li class="b_algo".*?</li>', re.S)
BING_LINK = re.compile(r'<h2>.*?<a[^>]*href="([^"]+)"', re.S)
BING_TITLE = re.compile(r"<h2>(.*?)</h2>", re.S)
BING_SNIP = re.compile(r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', re.S)


def _unwrap_bing(url: str) -> str:
    """Bing membungkus tautan hasil: /ck/a?...&u=a1<base64url>."""
    if "bing.com/ck/a" not in url:
        return url
    raw = url.replace("&amp;", "&")
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
    value = (qs.get("u") or [""])[0]
    if not value:
        return url
    body = value[2:] if value.startswith("a1") else value
    try:
        return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return url


def search_bing_html(query: str, timeout: int = 25) -> list[dict]:
    """Halaman hasil Bing. Lebih banyak dan lebih segar daripada RSS-nya."""
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({
        "q": query, "count": 30, "setlang": "id", "cc": "ID",
        "filters": 'ex1:"ez1"',       # 24 jam terakhir
    })
    page = _get(url, timeout=timeout).decode("utf-8", "replace")
    out = []
    for block in BING_BLOCK.findall(page):
        link = BING_LINK.search(block)
        if not link:
            continue
        href = _unwrap_bing(link.group(1))
        if not href.startswith("http"):
            continue
        title = BING_TITLE.search(block)
        snip = BING_SNIP.search(block)
        out.append({
            "url": href,
            "title": _clean(title.group(1)) if title else "",
            "snippet": _clean(snip.group(1))[:600] if snip else "",
            "published": None,
        })
    return out


# ---------------------------------------------------------------- yandex
_YANDEX_CRED: dict[str, str] = {"user": "", "key": ""}


def configure_yandex(user: str, key: str) -> None:
    _YANDEX_CRED["user"] = user or ""
    _YANDEX_CRED["key"] = key or ""


def search_yandex_xml(query: str, timeout: int = 25) -> list[dict]:
    """Yandex Search API (XML). Butuh user + key gratis dari yandex.ru/dev/xml."""
    if not (_YANDEX_CRED["user"] and _YANDEX_CRED["key"]):
        raise RuntimeError("YANDEX_USER / YANDEX_KEY belum diisi")
    url = "https://yandex.com/search/xml?" + urllib.parse.urlencode({
        "user": _YANDEX_CRED["user"], "key": _YANDEX_CRED["key"],
        "query": query, "lr": 10000, "filter": "strict",
        "groupby": "attr=d.mode=deep.groups-on-page=10.docs-in-group=1",
    })
    xml = _get(url, timeout=timeout).decode("utf-8", "replace")
    out = []
    for doc in re.findall(r"<doc[^>]*>(.*?)</doc>", xml, re.S):
        def tag(name: str) -> str:
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", doc, re.S)
            return _clean(m.group(1)) if m else ""
        link = tag("url")
        if not link:
            continue
        out.append({
            "url": link,
            "title": tag("title"),
            "snippet": (tag("passage") or tag("headline"))[:600],
            "published": parse_date(tag("last-modified") or tag("pubDate")),
        })
    return out


def search_yandex(query: str, timeout: int = 25) -> list[dict]:
    """Yandex HTML. Sering mendarat di /showcaptcha — kalau begitu hasil kosong."""
    url = "https://yandex.com/search/?" + urllib.parse.urlencode({"text": query, "lr": 10000})
    page = _get(url, timeout=timeout).decode("utf-8", "replace")
    if "showcaptcha" in page and "serp-item" not in page:
        # coba sekali lagi lewat host lain
        page = _get("https://yandex.ru/search/?" + urllib.parse.urlencode({"text": query}),
                    timeout=timeout).decode("utf-8", "replace")
    out = []
    for block in re.findall(r'class="[^"]*serp-item[^"]*"(.{0,4000}?)</li>', page, re.S):
        m = re.search(r'<a[^>]+href="(https?://[^"]+)"', block)
        if not m:
            continue
        t = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.S)
        out.append({
            "url": m.group(1),
            "title": _clean(t.group(1)) if t else "",
            "snippet": "",
            "published": None,
        })
    return out


# ---------------------------------------------------------------- github
def search_github(query: str, timeout: int = 20) -> list[dict]:
    url = "https://api.github.com/search/issues?" + urllib.parse.urlencode({
        "q": query, "sort": "created", "order": "desc", "per_page": 30,
    })
    raw = json.loads(_get(url, timeout=timeout).decode("utf-8", "replace"))
    out = []
    for it in raw.get("items", []):
        out.append({
            "url": it.get("html_url", ""),
            "title": it.get("title", ""),
            "snippet": (it.get("body") or "")[:600],
            "published": parse_date(it.get("created_at", "")),
        })
    return out


# ---------------------------------------------------------------- rss generik
def _parse_rss(xml: str) -> list[dict]:
    out = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", xml, re.S):
        def grab(tag: str) -> str:
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return _clean(m.group(1)) if m else ""
        link = grab("link")
        if not link:
            m = re.search(r'<link[^>]*href="([^"]+)"', block)
            link = m.group(1) if m else ""
        if not link:
            continue
        out.append({
            "url": link,
            "title": grab("title"),
            "snippet": (grab("description") or grab("content"))[:600],
            "published": parse_date(grab("pubDate") or grab("published")
                                    or grab("dc:date") or grab("updated")),
        })
    for block in re.findall(r"<entry[^>]*>(.*?)</entry>", xml, re.S):
        def grab2(tag: str) -> str:
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return _clean(m.group(1)) if m else ""
        link = ""
        m = re.search(r'<link[^>]*href="([^"]+)"', block)
        if m:
            link = m.group(1)
        if not link:
            continue
        out.append({
            "url": link,
            "title": grab2("title"),
            "snippet": (grab2("content") or grab2("summary"))[:600],
            "published": parse_date(grab2("published") or grab2("updated")),
        })
    return out


def search_rss(url: str, timeout: int = 25) -> list[dict]:
    raw = _get(url, timeout=timeout).decode("utf-8", "replace")
    stripped = raw.lstrip()
    if stripped.startswith("{"):
        return _parse_reddit_json(stripped)
    return _parse_rss(raw)


def _parse_reddit_json(payload: str) -> list[dict]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    out = []
    for child in data.get("data", {}).get("children", []):
        d = child.get("data", {})
        permalink = d.get("permalink")
        link = ("https://www.reddit.com" + permalink) if permalink else d.get("url", "")
        out.append({
            "url": link,
            "title": d.get("title", ""),
            "snippet": (d.get("selftext") or d.get("url_overridden_by_dest") or "")[:600],
            "published": int(d["created_utc"]) if d.get("created_utc") else None,
        })
    return out


# ---------------------------------------------------------------- google news
def search_gnews(query: str, timeout: int = 20) -> list[dict]:
    # when:1d dibaca Google News sebagai "terbit dalam 24 jam terakhir"
    q = query if "when:" in query else f"{query} when:1d"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": q, "hl": "id", "gl": "ID", "ceid": "ID:id",
    })
    raw = _get(url, timeout=timeout).decode("utf-8", "replace")
    return _parse_rss(raw)


# ---------------------------------------------------------------- hacker news
def search_hn(query: str, timeout: int = 20) -> list[dict]:
    cutoff = int(time.time()) - 24 * 3600
    url = "https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode({
        "query": query, "tags": "story", "hitsPerPage": 30,
        "numericFilters": f"created_at_i>{cutoff}",
    })
    data = json.loads(_get(url, timeout=timeout).decode("utf-8", "replace"))
    out = []
    for h in data.get("hits", []):
        link = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        out.append({
            "url": link,
            "title": h.get("title") or "",
            "snippet": (h.get("story_text") or h.get("comment_text") or "")[:600],
            "published": int(h["created_at_i"]) if h.get("created_at_i") else None,
        })
    return out


# ---------------------------------------------------------------- dev.to
def search_devto(query: str, timeout: int = 20) -> list[dict]:
    tag = re.sub(r"[^a-z0-9]", "", query.lower().split()[-1]) or "ai"
    url = f"https://dev.to/api/articles/latest?tag={tag}&per_page=30"
    data = json.loads(_get(url, timeout=timeout).decode("utf-8", "replace"))
    return [{
        "url": a.get("url", ""),
        "title": a.get("title", ""),
        "snippet": (a.get("description") or "")[:600],
        "published": parse_date(a.get("published_at", "")),
    } for a in data]


# ---------------------------------------------------------------- lemmy
def search_lemmy(query: str, instance: str = "lemmy.world", timeout: int = 25) -> list[dict]:
    url = f"https://{instance}/api/v3/search?" + urllib.parse.urlencode({
        "q": query, "type_": "Posts", "limit": 30, "sort": "New",
    })
    data = json.loads(_get(url, timeout=timeout).decode("utf-8", "replace"))
    out = []
    for p in data.get("posts", []):
        post = p.get("post", {})
        out.append({
            "url": post.get("url") or post.get("ap_id", ""),
            "title": post.get("name", ""),
            "snippet": (post.get("body") or "")[:600],
            "published": parse_date(post.get("published", "")),
        })
    return out


# ---------------------------------------------------------------- discourse
def search_discourse(base: str, query: str, after: str = "",
                     timeout: int = 20) -> list[dict]:
    """Forum Discourse (community.openai.com, forum.cursor.com, dst).

    `after` berformat YYYY-MM-DD dan memakai filter bawaan Discourse,
    jadi server yang menyaring, bukan kita.
    """
    base = base.rstrip("/")
    q = f"{query} after:{after}" if after else query
    url = f"{base}/search.json?" + urllib.parse.urlencode({"q": q})
    data = json.loads(_get(url, timeout=timeout).decode("utf-8", "replace"))
    topics = {str(t.get("id")): (t.get("title") or "") for t in data.get("topics", [])}
    out = []
    for post in data.get("posts", []):
        tid = str(post.get("topic_id", ""))
        if not tid:
            continue
        out.append({
            "url": f"{base}/t/{tid}/{post.get('post_number', 1)}",
            "title": topics.get(tid, "") or f"post #{tid}",
            "snippet": (post.get("blurb") or "")[:600],
            "published": parse_date(post.get("created_at", "")),
        })
    return out


# ---------------------------------------------------------------- mastodon
def search_mastodon(instance: str, query: str, timeout: int = 20) -> list[dict]:
    host = instance.replace("https://", "").replace("http://", "").strip("/")
    url = f"https://{host}/api/v2/search?" + urllib.parse.urlencode({
        "q": query, "type": "statuses", "limit": 40,
    })
    data = json.loads(_get(url, timeout=timeout).decode("utf-8", "replace"))
    out = []
    for st in data.get("statuses", []) or []:
        out.append({
            "url": st.get("url") or st.get("uri") or "",
            "title": _clean(st.get("content") or "")[:120],
            "snippet": _clean(st.get("content") or "")[:600],
            "published": parse_date(st.get("created_at", "")),
        })
    return out


# ---------------------------------------------------------------- reddit (oauth)
def search_reddit(query: str, timeout: int = 25) -> list[dict]:
    from . import reddit
    if not reddit.configured():
        raise RuntimeError("reddit belum dikonfigurasi (REDDIT_CLIENT_ID / SECRET)")
    return reddit.search(query)


# ---------------------------------------------------------------- orkestrasi
ENGINES = {
    "bing_html": search_bing_html,
    "yandex": search_yandex,
    "yandex_xml": search_yandex_xml,
    "reddit": search_reddit,
    "ddg": search_ddg,
    "bing": search_bing,
    "github": search_github,
    "gnews": search_gnews,
    "hn": search_hn,
    "devto": search_devto,
    "lemmy": search_lemmy,
}


def run_queries(queries: Iterable[str], engines: list[str],
                delay: tuple[float, float] = (3.0, 8.0),
                errors: list[str] | None = None) -> list[dict]:
    results: list[dict] = []
    for q in queries:
        for name in engines:
            fn = ENGINES.get(name)
            if not fn:
                continue
            try:
                items = fn(q)
                for it in items:
                    it["source"] = name
                    it["query"] = q
                results.extend(items)
            except Exception as exc:  # noqa: BLE001
                if errors is not None:
                    errors.append(f"{name}:{q[:40]}:{exc}")
            time.sleep(random.uniform(*delay))
    return results


def fetch_page(url: str, timeout: int = 20) -> str:
    """Ambil isi halaman untuk pencarian kode yang lebih dalam."""
    try:
        raw = _get(url, timeout=timeout, retries=2).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""
    return _clean(raw)[:20000]


def domain_of(url: str) -> str:
    return _domain(url)