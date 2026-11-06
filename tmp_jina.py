import urllib.error
import urllib.parse
import urllib.request

q = urllib.parse.quote_plus("kode promo ai gratis")
targets = {
    "jina_yandex": "https://r.jina.ai/https://yandex.com/search/?text=" + q,
    "jina_bing": "https://r.jina.ai/https://www.bing.com/search?q=" + q,
}
for name, url in targets.items():
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; pantau/1.0)",
        "Accept": "text/plain",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", "replace")
        cap = "not a robot" in body.lower() or "captcha" in body.lower()
        print(f"{name:12} {r.status} len={len(body):7} captcha={cap}")
        print("   ", body[:220].replace("\n", " "))
    except urllib.error.HTTPError as e:
        print(f"{name:12} HTTP {e.code} {e.read()[:120]}")
    except Exception as e:
        print(f"{name:12} ERR {str(e)[:80]}")
