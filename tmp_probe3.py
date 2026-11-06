import re
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
q = urllib.parse.quote_plus("kode promo ai gratis")

variants = {
    "plain": ("https://yandex.com/search/?text=" + q, {}),
    "cookie": ("https://yandex.com/search/?text=" + q,
               {"Cookie": "yandexuid=1234567891700000000; i=abc/def; yandex_gid=5"}),
    "lite": ("https://yandex.com/search/?text=" + q + "&lite=1", {}),
    "familia": ("https://yandex.com/search/?text=" + q + "&family=0", {"Accept": "text/html"}),
}

for name, (url, extra) in variants.items():
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Language", "id-ID,id;q=0.9,en;q=0.8")
    for k, v in extra.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
        tag = "CAPTCHA" if "not a robot" in body.lower() else "OK"
        hits = len(re.findall(r'class="[^"]*serp-item', body))
        print(f"{name:10} {tag:8} len={len(body):7} serp-item={hits}")
        if tag == "OK":
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S)
            print("   title:", (m.group(1) if m else "")[:80])
    except urllib.error.HTTPError as e:
        print(f"{name:10} HTTP {e.code}")
    except Exception as e:
        print(f"{name:10} ERR {e}")

print("\n--- isi halaman captcha (potongan) ---")
try:
    req = urllib.request.Request("https://yandex.com/search/?text=" + q)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        body = r.read().decode("utf-8", "replace")
    text = re.sub(r"<[^>]+>", " ", body)
    print(re.sub(r"\s+", " ", text)[:400])
except Exception as e:
    print("ERR", e)
