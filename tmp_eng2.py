import sys

sys.path.insert(0, ".")
from pantau import search

qs = ["claude gratis", "chatgpt plus gratis", "gemini gratis 12 bulan",
      "site:reddit.com claude promo code"]
for q in qs:
    try:
        rows = search.search_bing_html(q)
        print(f"{q:38} {len(rows)} hasil")
        for r in rows[:3]:
            print("    ", r["title"][:65])
    except Exception as exc:  # noqa: BLE001
        print(q, "ERR", exc)

print("\n-- yandex varian --")
for q in ["claude gratis"]:
    try:
        print("yandex:", len(search.search_yandex(q)))
    except Exception as exc:  # noqa: BLE001
        print("yandex ERR", exc)
