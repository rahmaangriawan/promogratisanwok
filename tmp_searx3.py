import json
import urllib.error
import urllib.parse
import urllib.request

q = "kode promo ai gratis"
instances = [
    "https://searx.be",
    "https://baresearch.org",
    "https://search.inetol.net",
    "https://searx.work",
    "https://searxng.site",
    "https://search.rhscz.eu",
    "https://searx.namejeff.xyz",
    "https://search.hbubli.cc",
    "https://searxng.brihx.fr",
    "https://search.sapti.me",
]

print("== POST + Accept json ==")
for base in instances:
    data = urllib.parse.urlencode({"q": q, "format": "json"}).encode()
    req = urllib.request.Request(f"{base}/search", data=data, method="POST")
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; pantau/1.0)")
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
        if body.lstrip().startswith(b"{"):
            d = json.loads(body)
            res = d.get("results", [])
            print(f"  {base:34} JSON {len(res)} hasil  {sorted({x.get('engine') for x in res})[:4]}")
        else:
            print(f"  {base:34} HTML/challenge ({len(body)}b)")
    except urllib.error.HTTPError as e:
        print(f"  {base:34} HTTP {e.code}")
    except Exception as e:
        print(f"  {base:34} ERR {str(e)[:40]}")

print("\n== yandex xml tanpa key ==")
u = "https://yandex.com/search/xml?user=demo&key=demo&query=" + urllib.parse.quote_plus(q)
try:
    with urllib.request.urlopen(u, timeout=20) as r:
        print("  status", r.status, r.read()[:200])
except urllib.error.HTTPError as e:
    print("  HTTP", e.code, e.read()[:250])
