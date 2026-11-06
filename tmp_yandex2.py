import re
import urllib.error
import urllib.parse
import urllib.request

q = urllib.parse.quote_plus("kode promo ai gratis")

UAS = {
    "googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "yandexbot": "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
    "textbrowser": "Lynx/2.8.9rel.1 libwww-FM/2.14 SSL-MM/1.4.1",
    "curl": "curl/8.7.1",
}

for name, ua in UAS.items():
    for host in ("https://yandex.com/search/?text=", "https://yandex.ru/search/?text="):
        req = urllib.request.Request(host + q)
        req.add_header("User-Agent", ua)
        req.add_header("Accept-Language", "id,en;q=0.8")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read().decode("utf-8", "replace")
            cap = "not a robot" in body.lower()
            items = len(re.findall(r"serp-item|OrganicTitle", body))
            print(f"{name:12} {host.split('/')[2]:12} {'CAPTCHA' if cap else 'OK':8} len={len(body):7} item={items}")
        except urllib.error.HTTPError as e:
            print(f"{name:12} {host.split('/')[2]:12} HTTP {e.code}")
        except Exception as e:
            print(f"{name:12} {host.split('/')[2]:12} ERR {str(e)[:40]}")
