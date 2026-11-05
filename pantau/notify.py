"""notify.py — kirim temuan ke Discord / Telegram. Tanpa library eksternal."""

from __future__ import annotations

import json
import time
import urllib.request


def _post(url: str, payload: dict, timeout: int = 15) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "pantau/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _get(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "pantau/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _codes(item: dict) -> list[str]:
    try:
        return json.loads(item.get("codes") or "[]")
    except (TypeError, ValueError):
        return []


def _line(it: dict) -> str:
    codes = json.loads(it.get("codes") or "[]")
    tag = ", ".join(codes) if codes else "-"
    extra = f" (s/d {it['expiry']})" if it.get("expiry") else ""
    return f"[{it['score']}] {it['title'][:80]}\nkode: {tag}{extra}\n{it['url']}"


def _discord_msg(items: list[dict]) -> str:
    lines = []
    for it in items:
        codes = _codes(it)
        tag = "`" + "`, `".join(codes) + "`" if codes else "_(tanpa kode)_"
        extra = f" · s/d {it['expiry']}" if it.get("expiry") else ""
        lines.append(f"**{it['title'][:110]}**\n{tag}\nskor {it['score']}{extra}\n{it['url']}")
    return ("**temuan baru**\n\n" + "\n\n".join(lines))[:1900]


def send_discord(webhook: str, items: list[dict]) -> bool:
    if not webhook or not items:
        return False
    ok = False
    for i in range(0, len(items), 5):
        res = _post(webhook, {"content": _discord_msg(items[i:i + 5]),
                              "allowed_mentions": {"parse": []}})
        ok = res.get("ok", True) is not False or ok
    return ok


def telegram_text(items: list[dict]) -> str:
    head = f"{len(items)} temuan baru\n"
    return (head + "\n" + "\n\n".join(_line(i) for i in items[:12]))[:4000]


def resolve_chat(token: str, timeout_s: int = 0) -> str | None:
    """Ambil chat_id dari pesan terakhir yang masuk ke bot.

    timeout_s > 0 akan menunggu sampai ada pesan masuk (polling ringan).
    """
    deadline = time.time() + timeout_s
    while True:
        data = _get(f"https://api.telegram.org/bot{token}/getUpdates?limit=20")
        for upd in data.get("result", []) or []:
            msg = (upd.get("message") or upd.get("edited_message")
                   or upd.get("channel_post") or upd.get("my_chat_member") or {})
            chat = msg.get("chat") or {}
            if chat.get("id"):
                return str(chat["id"])
        if time.time() >= deadline:
            return None
        time.sleep(3)


def send_telegram(token: str, chat: str, items: list[dict]) -> bool:
    if not (token and items):
        return False
    if not chat:
        chat = resolve_chat(token) or ""
    if not chat:
        return False
    ok = False
    for i in range(0, len(items), 5):
        res = _post(f"https://api.telegram.org/bot{token}/sendMessage", {
            "chat_id": chat,
            "text": telegram_text(items[i:i + 5]),
            "disable_web_page_preview": True,
        })
        ok = bool(res.get("ok")) or ok
    return ok


def send_plain(token: str, chat: str, text: str) -> bool:
    if not chat:
        chat = resolve_chat(token) or ""
    if not chat:
        return False
    res = _post(f"https://api.telegram.org/bot{token}/sendMessage",
                {"chat_id": chat, "text": text[:4000],
                 "disable_web_page_preview": True})
    return bool(res.get("ok"))


def bot_info(token: str) -> dict:
    return _get(f"https://api.telegram.org/bot{token}/getMe")