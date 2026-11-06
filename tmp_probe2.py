import re
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def get(url, ua=UA):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", ua)
    req.add_header("Accept-Language", "id-ID,id;q=0.9,en;q=0.8")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"ERR {e}"


q = urllib.parse.quote_plus("kode promo ai gratis")

st, body = get(f"https://www.bing.com/search?q={q}&count=30&setlang=id&cc=ID")
print("bing status", st, "b_algo:", body.count("b_algo"), "| li class=:", len(re.findall(r"<li class=\"b_", body)))
i = body.find("b_results")
print(repr(body[i:i + 1200]))

print("\n--- yandex mobile ---")
for url in (f"https://yandex.com/search/touch/?text={q}",
            f"https://yandex.com/search/?text={q}&noreask=1"):
    st, body = get(url, MOBILE)
    print(url[:48], st, len(body), "captcha" if "captcha" in body.lower() else "ok")
