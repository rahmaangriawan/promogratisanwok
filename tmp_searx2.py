import re
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
q = urllib.parse.quote_plus("kode promo ai gratis")

for url in (f"https://searx.be/search?q={q}",
            f"https://searx.be/search?q={q}&engines=yandex",
            f"https://searx.be/search?q={q}&engines=bing"):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
        arts = re.findall(r'<article class="result', body)
        print(url.split("?")[1][:40], "len", len(body), "hasil", len(arts))
        m = re.findall(r'<a href="(http[^"]+)"[^>]*class="url_header"', body)
        print("   contoh:", m[:2])
        if not arts:
            print("   ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))[:180])
    except urllib.error.HTTPError as e:
        print(url.split("?")[1][:40], "HTTP", e.code)
    except Exception as e:
        print(url.split("?")[1][:40], "ERR", str(e)[:50])
