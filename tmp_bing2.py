import base64
import re
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def unwrap(url):
    """Bing membungkus tautan: /ck/a?...&u=a1<base64url>"""
    if "bing.com/ck/a" not in url:
        return url
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url.replace("&amp;", "&")).query)
    raw = (qs.get("u") or [""])[0]
    if not raw:
        return url
    body = raw[2:] if raw.startswith("a1") else raw
    pad = "=" * (-len(body) % 4)
    try:
        return base64.urlsafe_b64decode(body + pad).decode("utf-8", "replace")
    except Exception:
        return url


q = urllib.parse.quote_plus("kode promo ai gratis")
for count in (10, 30, 50):
    url = f"https://www.bing.com/search?q={q}&count={count}&setlang=en&cc=US"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        body = r.read().decode("utf-8", "replace")
    blocks = re.findall(r'<li class="b_algo".*?</li>', body, re.S)
    print(f"count={count} blok={len(blocks)}")
    for b in blocks[:2]:
        m = re.search(r'<h2>.*?<a[^>]*href="([^"]+)"', b, re.S)
        t = re.search(r"<h2>(.*?)</h2>", b, re.S)
        if m:
            print("   ", unwrap(m.group(1).replace("&amp;", "&"))[:80])
            print("    title:", re.sub(r"<[^>]+>", "", t.group(1))[:60] if t else "-")
