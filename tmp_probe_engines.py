import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def get(url, extra=None):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Language", "id-ID,id;q=0.9,en;q=0.8")
    req.add_header("Accept", "text/html,application/xhtml+xml")
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:600]
    except Exception as e:
        return 0, f"ERR {e}"


q = "kode promo ai gratis"
enc = urllib.parse.quote_plus(q)

targets = {
    "bing_html": f"https://www.bing.com/search?q={enc}&count=30&setlang=id&cc=ID",
    "yandex_html": f"https://yandex.com/search/?text={enc}&lr=10000",
    "yandex_com_tr": f"https://yandex.com.tr/search/?text={enc}",
    "yandex_ru": f"https://yandex.ru/search/?text={enc}",
    "yandex_xml": f"https://yandex.com/search/xml?user=x&key=y&query={enc}",
}

for name, url in targets.items():
    st, body = get(url)
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    t = (title.group(1).strip()[:60] if title else body[:60]).replace("\n", " ")
    print(f"{name:16} {st} len={len(body):7} {t}")

print("\n=== cek penanda anti-bot ===")
st, body = get(f"https://www.bing.com/search?q={enc}")
for marker in ("captcha", "unusual traffic", "showcaptcha", "b_results", "b_algo"):
    print(f"bing {marker:16}", marker in body.lower())

st, body = get(f"https://yandex.com/search/?text={enc}")
for marker in ("captcha", "robot", "smartcaptcha", "serp-item", "CheckboxCaptcha"):
    print(f"yandex {marker:16}", marker in body.lower())
