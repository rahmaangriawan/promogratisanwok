import sys

sys.path.insert(0, ".")
from pantau import search

for name, fn in (("bing_html", search.search_bing_html), ("yandex", search.search_yandex)):
    try:
        rows = fn("kode promo ai gratis")
        print(f"{name:10} {len(rows)} hasil")
        for r in rows[:3]:
            print("   ", r["title"][:60], "|", r["url"][:70])
    except Exception as exc:  # noqa: BLE001
        print(f"{name:10} ERROR {exc}")
