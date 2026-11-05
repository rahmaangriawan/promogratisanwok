"""ekstrak.py — tarik kode promo / voucher dari teks mentah.

Pendekatan: pola regex berlapis + penyaringan stop-word.
Kode promo umumnya: KLAIM50, CLAUDE20, FREEPRO, AI-2026, dll.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- pola kandidat kode ------------------------------------------------
# 4-24 karakter, huruf besar/angka, boleh ada - atau _
PATTERNS = [
    # dalam tanda kutip / backtick / bold: "CODE50"  `CODE50`  **CODE50**
    re.compile(r'[`"\'\u201c\u201d]([A-Z0-9][A-Z0-9_-]{3,23})[`"\'\u201c\u201d]'),
    # setelah kata kunci
    re.compile(
        r'(?:kode|code|voucher|promo|redeem|gunakan|pakai|use|with|invite)\s*'
        r'(?:promo|voucher|kode)?\s*[:=]?\s*([A-Z0-9][A-Z0-9_-]{3,23})\b',
        re.IGNORECASE,
    ),
    # token ALLCAPS berdiri sendiri
    re.compile(r'\b([A-Z][A-Z0-9]{3,19}(?:[-_][A-Z0-9]{2,12}){0,3})\b'),
]

# --- buang yang jelas bukan kode --------------------------------------
STOPWORDS = {
    "HTTP", "HTTPS", "HTML", "WWW", "JSON", "YAML", "API", "SDK", "URL", "URI",
    "SSD", "CPU", "GPU", "RAM", "USB", "PDF", "RSS", "SEO", "ADS", "LLM", "GPT",
    "OPENAI", "CLAUDE", "GEMINI", "CHATGPT", "ANTHROPIC", "COPILOT", "CURSOR",
    "PERPLEXITY", "DEEPSEEK", "MIDJOURNEY", "ELEVENLABS", "WINDSURF",
    "EDIT", "NEW", "FREE", "PRO", "PLUS", "MAX", "TEAM", "TRIAL", "USER",
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
    "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER", "MONDAY", "TUESDAY",
    "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY",
    "INDONESIA", "JAKARTA", "UPDATE", "LOGIN", "SIGNUP", "ACCOUNT",
    "TERMS", "PRIVACY", "COOKIE", "CONTACT", "ABOUT", "HELP", "SUPPORT",
}

def _plausible(code: str, context: str, quoted: bool = False) -> bool:
    if code in STOPWORDS:
        return False
    # kode promo selalu huruf besar penuh — tolak "Claude", "ChatGPT", "kode ini"
    if code != code.upper():
        return False
    if len(code) < 4 or len(code) > 24:
        return False
    if code_is_junk(code):
        return False
    if code.isdigit():
        return False
    has_digit = any(ch.isdigit() for ch in code)
    has_alpha = any(ch.isalpha() for ch in code)
    if not has_alpha:
        return False
    # kode promo hampir selalu memuat angka. Tanpa angka: hanya lolos kalau
    # token dikutip/di-backtick DAN ada kata promo kuat di sekitarnya.
    if not has_digit:
        if not quoted:
            return False
        strong = ("kode promo", "kode voucher", "kode redeem", "promo code",
                  "voucher code", "coupon code", "redeem code", "kode undangan",
                  "invite code", "referral code")
        if not any(w in context.lower() for w in strong):
            return False
    # token dengan garis bawah tanpa angka = nama variabel/konstanta
    if "_" in code and not has_digit:
        return False
    if code.count("-") >= 2 and not has_digit:
        return False
    # harus dekat kata kunci promo di sekitar
    window = context.lower()
    near = any(w in window for w in (
        "kode", "code", "voucher", "promo", "redeem", "diskon", "discount",
        "gratis", "free", "trial", "coupon", "invite", "referral",
    ))
    return near


def extract_codes(text: str, limit: int = 12) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pat in PATTERNS:
        for m in pat.finditer(text):
            code = m.group(1).strip("-_")
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 80)
            context = text[start:end]
            head = text[max(0, m.start() - 1):m.start()]
            quoted = head in ('"', "'", "`", "\u201c", "\u201d", "*")
            if not _plausible(code, context, quoted=quoted):
                continue
            if code in seen:
                continue
            seen.add(code)
            found.append(code)
            if len(found) >= limit:
                return found
    return found


# --- deteksi merek ----------------------------------------------------
BRANDS: dict[str, tuple[str, ...]] = {
    "claude":       ("claude", "anthropic", "claude pro", "claude max"),
    "chatgpt":      ("chatgpt", "openai", "gpt-4", "gpt-5", "gpt4", "gpt"),
    "gemini":       ("gemini", "google ai", "bard", "google one ai"),
    "copilot":      ("copilot", "github copilot"),
    "cursor":       ("cursor", "cursor.sh", "cursor ai"),
    "perplexity":   ("perplexity", "pplx"),
    "deepseek":     ("deepseek",),
    "midjourney":   ("midjourney", "mj "),
    "elevenlabs":   ("elevenlabs", "eleven labs"),
    "windsurf":     ("windsurf", "codeium"),
    "kiro":         ("kiro", "aws kiro"),
    "vercel":       ("v0", "vercel"),
    "grok":         ("grok", "x.ai", "xai"),
    "mistral":      ("mistral", "le chat"),
    "poe":          ("poe.com", "poe ai"),
}

# kata yang menandakan ini promo aktif, bukan sekadar artikel
PROMO_SIGNALS = (
    "gratis", "free", "trial", "promo", "voucher", "kode", "code", "redeem",
    "diskon", "discount", "coupon", "klaim", "claim", "bonus", "credit",
    "kuota", "quota", "giveaway", "hadiah", "100%", "off", "monet",
)

# kata yang menandakan sudah kedaluwarsa
DEAD_SIGNALS = (
    "expired", "kedaluwarsa", "kadaluarsa", "sudah berakhir", "ended",
    "no longer valid", "tidak berlaku lagi", "habis", "sold out",
    "invalid code", "kode tidak valid",
)


def detect_brand(text: str) -> str:
    low = text.lower()
    for brand, keys in BRANDS.items():
        if any(k in low for k in keys):
            return brand
    return ""


PROMO_WORDS = ("gratis", "free", "promo", "voucher", "trial", "diskon",
               "discount", "klaim", "claim", "giveaway", "coupon", "bonus",
               "murah", "credit", "kredit", "kuota", "cuma-cuma")


NOT_OFFER = (
    "promo video", "video promo", "promosi", "iklan", "show hn", "showoff",
    "i made", "i built", "i created", "we built", "we made", "my app",
    "looking for feedback", "roast my", "rate my",
)


def is_offer(title: str, snippet: str, codes: list[str]) -> bool:
    """Apakah ini penawaran (promo/bansos), bukan sekadar obrolan soal AI?

    Lolos kalau ada kode konkret, atau judulnya menyebut merek AI + kata promo.
    """
    if codes:
        return True
    low_title = title.lower()
    if any(p in low_title for p in NOT_OFFER):
        return False
    low_snip = snippet.lower()
    brand_tokens = {k for keys in BRANDS.values() for k in keys}
    # "ai" umum ikut dihitung, tapi hanya kalau ada kata promo di judul
    generic = ("ai", "kecerdasan buatan", "chatbot", "asisten ai", "model bahasa")
    has_brand = any(tok in low_title for tok in brand_tokens) or any(g in low_title for g in generic)
    has_promo = any(w in low_title for w in PROMO_WORDS)
    if has_brand and has_promo:
        return True
    # judul datar tapi cuplikan jelas menawarkan sesuatu
    return (any(tok in low_snip for tok in brand_tokens)
            and any(w in low_snip for w in PROMO_WORDS)
            and any(w in low_title for w in PROMO_WORDS + ("ai", "openai", "claude")))


# --- sumbu AI: hasil wajib menyentuh salah satu ini -------------------
AI_AXIS = (
    "ai", "llm", "claude", "anthropic", "chatgpt", "openai", "gpt", "gemini",
    "copilot", "cursor", "perplexity", "pplx", "deepseek", "midjourney",
    "elevenlabs", "windsurf", "codeium", "kiro", "grok", "xai", "mistral",
    "poe", "v0", "vercel", "nebius", "groq", "together ai", "huggingface",
    "obrolan ai", "asisten ai", "model bahasa", "kecerdasan buatan",
    "bansos ai", "token ai", "api ai", "ai gratis", "kredit api", "kredit ai",
    "free api", "token api", "kuota api", "ai starter",
)

# pola yang jelas sampah non-promo
JUNK_PATTERNS = (
    "kode pos", "kode wilayah", "kode bank", "kode negara", "kode plat",
    "kode kbli", "kode kbki", "kode kbbi", "arti kata", "kamus",
    "kode apk", "apkmirror", "kode redeem game", "kode voucher ml",
    "mobile legends", "free fire", "ff max", "redeem ff", "codm", "valorant",
    "roblox", "dragon city", "pubg", "genshin", "kode undangan",
    "kode referral bank", "kode OTP", "kode verifikasi",
)

# token yang format kode tapi jelas bukan voucher
JUNK_CODE_RE = (
    re.compile(r"^G-[A-Z0-9]{8,}$"),        # google analytics
    re.compile(r"^UA-\d+-\d+$"),            # analytics lama
    re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}"),  # uuid
    re.compile(r"^\d{5,6}$"),               # kode pos
)


def is_relevant(title: str, snippet: str, url: str) -> bool:
    """True kalau hasil ini benar-benar soal layanan AI, bukan 'kode' generik."""
    text = f"{title} {snippet} {url}".lower()
    if any(j.lower() in text for j in JUNK_PATTERNS):
        return False
    padded = f" {text} "
    for term in AI_AXIS:
        if term == "ai":
            if " ai " in padded or "ai." in padded or "/ai" in padded or "ai-" in padded:
                return True
            continue
        if term in text:
            return True
    return False


def code_is_junk(code: str) -> bool:
    if any(p.match(code) for p in JUNK_CODE_RE):
        return True
    # token panjang tanpa pemisah = biasanya ID teknis (analytics, hash)
    if len(code) >= 10 and "-" not in code and "_" not in code:
        if sum(ch.isdigit() for ch in code) < 2:
            return True
    return False


def score_finding(title: str, snippet: str, url: str, domain: str,
                  codes: list[str], trust: dict[str, int],
                  source: str = "") -> int:
    """Skor 0-100. Makin tinggi makin layak dilihat manusia."""
    text = f"{title} {snippet}".lower()
    s = 0

    # ada kode konkret = sinyal terkuat
    s += min(40, len(codes) * 18)

    # sinyal promo
    signals = sum(1 for w in PROMO_SIGNALS if w in text)
    s += min(20, signals * 5)

    # judul memuat kata promo/gratis
    if any(w in title.lower() for w in ("promo", "gratis", "free", "voucher", "kode", "code")):
        s += 10

    # tahun berjalan di judul/url = segar
    if "2026" in text or "2026" in url:
        s += 8

    # kepercayaan domain
    s += trust.get(domain, 0) * 2

    # hukuman: tanda kedaluwarsa
    if any(w in text for w in DEAD_SIGNALS):
        s -= 35

    # hukuman: halaman jualan / agregator sampah
    junk = ("login", "signin", "sign-in", "cart", "checkout", "privacy-policy")
    if any(j in url.lower() for j in junk):
        s -= 25

    # hukuman: judul terlalu pendek / kosong
    if len(title.strip()) < 12:
        s -= 15

    # hukuman: tidak menyentuh layanan AI sama sekali
    if not is_relevant(title, snippet, url):
        s -= 40

    # github penuh commit/PR yang menyebut "promo" tanpa kode apa pun
    if "github" in source and not codes:
        s -= 22

    return max(0, min(100, s))

MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11,
    "desember": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "agu": 8, "agt": 8, "aug": 8, "sept": 9, "oct": 10, "dec": 12, "sep": 9, "okt": 10, "nov": 11, "des": 12,
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "august": 8, "october": 10, "december": 12,
}

EXPIRY_RE = re.compile(
    r"(?:hingga|sampai|berlaku|valid|expires?|expired?|until|till|deadline)"
    r"[^0-9]{0,18}(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})",
    re.I,
)


def guess_expiry(text: str) -> str | None:
    """Ambil tanggal kedaluwarsa kalau disebut eksplisit. Format ISO atau None."""
    for m in EXPIRY_RE.finditer(text):
        day, month_name, year = m.groups()
        month = MONTHS.get(month_name.lower())
        if not month:
            continue
        try:
            return f"{int(year):04d}-{month:02d}-{int(day):02d}"
        except ValueError:
            continue
    return None
