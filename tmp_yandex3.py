import re
import urllib.error
import urllib.parse
import urllib.request

q = urllib.parse.quote_plus("kode promo ai gratis")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "identity",
    "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}

hosts = ["https://yandex.com/search/?text=", "https://ya.ru/search/?text=",
         "https://yandex.com.tr/search/?text="]

for host in hosts:
    req = urllib.request.Request(host + q, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
        cap = "showcaptcha" in r.geturl() or "not a robot" in body.lower()
        items = len(re.findall(r"serp-item|OrganicTitle|organic__url", body))
        print(f"{host.split('/')[2]:16} {'CAPTCHA' if cap else 'OK':8} len={len(body):7} item={items} final={r.geturl()[:48]}")
        if not cap:
            for m in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*Link[^"]*"', body):
                print("   ", m.group(1)[:80])
                break
    except urllib.error.HTTPError as e:
        print(f"{host.split('/')[2]:16} HTTP {e.code}")
    except Exception as e:
        print(f"{host.split('/')[2]:16} ERR {str(e)[:50]}")
