import re
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
q = urllib.parse.quote_plus("kode promo ai gratis")

# variasi Bing: json hasil terstruktur (b_algo) + tanggal
for url in (f"https://www.bing.com/search?q={q}&format=rss",
            f"https://www.bing.com/search?q={q}&count=50&first=1"):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "id-ID,id;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception as e:
        print("ERR", e)
        continue
    if body.lstrip().startswith("<?xml"):
        items = re.findall(r"<item>(.*?)</item>", body, re.S)
        print("RSS item:", len(items))
        if items:
            print("  title:", re.search(r"<title>(.*?)</title>", items[0], re.S).group(1)[:60])
            print("  pubDate:", (re.search(r"<pubDate>(.*?)</pubDate>", items[0], re.S) or ["", "-"])[1][:40])
        continue

    blocks = re.findall(r'<li class="b_algo".*?</li>', body, re.S)
    print("HTML b_algo:", len(blocks))
    for b in blocks[:3]:
        t = re.search(r"<h2>.*?<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", b, re.S)
        if t:
            print("  ", re.sub(r"<[^>]+>", "", t.group(2))[:60], "|", t.group(1)[:70])
