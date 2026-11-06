import http.cookiejar
import re
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [("User-Agent", UA),
                     ("Accept-Language", "id-ID,id;q=0.9,en;q=0.8"),
                     ("Accept", "text/html,application/xhtml+xml")]

q = urllib.parse.quote_plus("kode promo ai gratis")

print("1) hangatkan sesi di beranda")
try:
    r = opener.open("https://yandex.com/", timeout=25)
    r.read()
    print("   status", r.status, "cookies:", [c.name for c in jar])
except Exception as e:
    print("   ERR", e)

print("2) cari")
try:
    r = opener.open(f"https://yandex.com/search/?text={q}&lr=10000", timeout=25)
    body = r.read().decode("utf-8", "replace")
    cap = "showcaptcha" in r.geturl()
    print("   status", r.status, "captcha:", cap, "len", len(body))
    items = re.findall(r'class="[^"]*serp-item', body)
    print("   serp-item:", len(items))
    if items:
        m = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.S)
        if m:
            print("   contoh:", re.sub(r"<[^>]+>", "", m.group(2))[:60], "|", m.group(1)[:70])
except Exception as e:
    print("   ERR", e)
