import json
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; pantau/1.0)"

INSTANCES = [
    "https://searx.be",
    "https://searxng.site",
    "https://search.bus-hit.me",
    "https://searx.tiekoetter.com",
    "https://priv.au",
    "https://opnxng.com",
    "https://searxng.world",
    "https://baresearch.org",
    "https://search.inetol.net",
    "https://searx.work",
    "https://paulgo.io",
]

q = urllib.parse.quote_plus("kode promo ai gratis")

for base in INSTANCES:
    url = f"{base}/search?q={q}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
        if body.lstrip().startswith(b"{"):
            data = json.loads(body)
            engines = sorted({x.get("engine") for x in data.get("results", [])})
            print(f"{base:32} JSON ok  hasil={len(data.get('results', []))} engines={engines[:6]}")
        else:
            print(f"{base:32} HTML saja ({len(body)} b)")
    except urllib.error.HTTPError as e:
        print(f"{base:32} HTTP {e.code}")
    except Exception as e:
        print(f"{base:32} ERR {str(e)[:50]}")
