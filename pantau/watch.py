"""watch.py — jalur cepat khusus tautan referral / bansos slot terbatas.

Referral seperti https://claude.ai/referral/GUvbjAH4HQ habis dalam hitungan
menit karena kuotanya dibatasi. Karena itu jalur ini:

  * hanya menyentuh sumber yang ramai (kanal Telegram publik, subreddit /new)
  * tidak memakai skor ambang — tautan referral baru SELALU dikirim
  * tidak membuka halaman, tanpa deep scan, jadi satu putaran < 10 detik

Semua temuan tetap disimpan ke DB yang sama supaya dedupe berlaku.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

from . import extract, notify
from .store import Finding, Store

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# tautan referral merek yang dikenal — prioritas tertinggi
REF_KNOWN = re.compile(
    r"https?://(?:www\.)?(?:"
    r"claude\.ai/referral"
    r"|chatgpt\.com/invite"
    r"|openai\.com/invite"
    r"|grok\.com/referral"
    r"|x\.ai/invite"
    r"|perplexity\.ai/invite"
    r"|cursor\.com/referral"
    r"|poe\.com/invite"
    r"|deepseek\.com/invite"
    r"|chat\.deepseek\.com/invite"
    r"|z\.ai/invite"
    r"|kimi\.com/invite"
    r"|qwen\.ai/invite"
    r"|gemini\.google\.com/share"
    r"|agentrouter\.org"
    r"|openrouter\.ai"
    r"|together\.ai"
    r"|groq\.com"
    r"|huggingface\.co/join"
    r"|puter\.com"
    r"|copilot\.microsoft\.com/invite"
    r"|agentrouter\.org/register"
    r")[^\s\"'<>)]*",
    re.I,
)

# referral generik: ?ref= / ?invite= / ?code= dengan kode 4+ karakter.
# Ini menangkap tautan affiliate toko juga, jadi wajib disaring.
REF_GENERIC = re.compile(
    r"https?://[^\s\"'<>)]{10,140}?[?&](?:ref|referral|invite|code|aff|partner)=[A-Za-z0-9_-]{4,}",
    re.I,
)

# domain afiliasi / toko: bukan bansos AI, selalu dibuang
AFFILIATE = (
    "amazon.", "myntr.in", "bilty.co", "flipkart", "aliexpress", "shopee",
    "tokopedia", "lazada", "bukalapak", "tiktok.com", "bit.ly", "linktr.ee",
    "amzn.to", "fkrt.it", "cuelinks", "earnkaro", "invl.io", "dl.flipkart",
)

POST_TEXT = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
POST_DATE = re.compile(r'<time[^>]+datetime="([^"]+)"')
POST_LINK = re.compile(r'<a class="tgme_widget_message_date" href="([^"]+)"')


def _strip(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    import html as _html
    return re.sub(r"[ \t]+", " ", _html.unescape(text)).strip()


def _fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc


def parse_channel(page: str, channel: str) -> list[dict]:
    texts = [_strip(t) for t in POST_TEXT.findall(page)]
    dates = POST_DATE.findall(page)
    links = POST_LINK.findall(page)
    out = []
    for i, text in enumerate(texts):
        published = None
        if i < len(dates):
            try:
                from .search import parse_date
                published = parse_date(dates[i])
            except Exception:  # noqa: BLE001
                published = None
        out.append({
            "text": text,
            "published": published,
            "url": links[i] if i < len(links) else f"https://t.me/{channel}",
            "channel": channel,
        })
    return out


def _is_affiliate(link: str) -> bool:
    low = link.lower()
    return any(d in low for d in AFFILIATE)


def referral_links(text: str) -> list[tuple[str, int]]:
    """(tautan, skor) — 100 untuk merek dikenal, 70 untuk generik berkonteks AI."""
    found: list[tuple[str, int]] = []
    seen: set[str] = set()
    for match in REF_KNOWN.finditer(text):
        link = match.group(0).rstrip(".,)")
        if link not in seen:
            seen.add(link)
            found.append((link, 100))

    # tautan generik hanya diterima kalau post-nya bicara soal AI
    has_ai_context = extract.is_relevant(text, "", "") or extract.detect_brand(text)
    if has_ai_context:
        for match in REF_GENERIC.finditer(text):
            link = match.group(0).rstrip(".,)")
            if link in seen or _is_affiliate(link):
                continue
            seen.add(link)
            found.append((link, 70))
    return found


def scan(cfg: dict, store: Store, dry: bool = False) -> tuple[int, int]:
    """Kembalikan (jumlah temuan, jumlah terkirim)."""
    max_age = int(cfg.get("max_age_hours", 24)) * 3600
    cutoff = int(time.time()) - max_age
    trust = {k.lower(): v for k, v in (cfg.get("trust") or {}).items()}

    found: list[Finding] = []
    errors: list[str] = []

    for channel in cfg.get("telegram_channels") or []:
        try:
            page = _fetch(f"https://t.me/s/{channel}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tg:{channel}:{exc}")
            continue
        for post in parse_channel(page, channel):
            if post["published"] and post["published"] < cutoff:
                continue
            refs = referral_links(post["text"])
            codes = extract.extract_codes(post["text"])
            if not refs and not codes:
                continue
            # tiap tautan referral jadi temuan sendiri supaya cepat diklik
            for link, base in refs:
                found.append(Finding(
                    url=link,
                    domain="t.me",
                    title=(post["text"].splitlines()[0] or link)[:140],
                    snippet=post["text"][:400],
                    source=f"tg:{channel}",
                    brand=extract.detect_brand(post["text"]),
                    codes=codes,
                    score=base,
                    published=post["published"],
                    raw={"post": post["url"]},
                ))
            if codes and not refs:
                found.append(Finding(
                    url=post["url"],
                    domain="t.me",
                    title=(post["text"].splitlines()[0] or "post")[:140],
                    snippet=post["text"][:400],
                    source=f"tg:{channel}",
                    brand=extract.detect_brand(post["text"]),
                    codes=codes,
                    score=60,
                    published=post["published"],
                    raw={"post": post["url"]},
                ))
        time.sleep(0.5)

    fresh = [f for f in found if store.upsert(f)]
    fresh.sort(key=lambda f: (-f.score, f.title))

    sent = 0
    if fresh and not dry:
        token = (cfg.get("notify") or {}).get("telegram_token") or ""
        chat = (cfg.get("notify") or {}).get("telegram_chat") or ""
        if token:
            if not chat:
                chat = store.get_setting("telegram_chat")
            if chat and notify.send_telegram(token, chat, [f.__dict__ for f in fresh]):
                store.mark_notified([f.uid for f in fresh])
                sent = len(fresh)

    if errors:
        print("[watch] galat: " + "; ".join(errors[:3]))
    return len(found), sent
