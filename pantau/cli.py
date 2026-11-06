"""cli.py — jalankan satu putaran pelacakan, cetak hasil, simpan."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import yaml

from . import extract, notify, reddit, search
from .store import Finding, Store


ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _load_dotenv(path: str = ".env") -> None:
    """Baca .env tanpa dependency tambahan; variabel lama tidak ditimpa."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _expand_env(value):
    if isinstance(value, str):
        return ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_cfg(path: str) -> dict:
    _load_dotenv()
    with open(path, encoding="utf-8") as fh:
        return _expand_env(yaml.safe_load(fh))


def expand(queries: list[str]) -> list[str]:
    now = dt.datetime.now()
    months_id = ["januari", "februari", "maret", "april", "mei", "juni", "juli",
                 "agustus", "september", "oktober", "november", "desember"]
    out = []
    for q in queries:
        out.append(q.format(year=now.year, month=months_id[now.month - 1]))
    return out


def harvest(cfg: dict, run_id: int = 0) -> tuple[list[Finding], list[str]]:
    errors: list[str] = []
    delay = (cfg["rate"]["delay_min"], cfg["rate"]["delay_max"])
    trust = {k.lower(): v for k, v in (cfg.get("trust") or {}).items()}

    rcfg = cfg.get("reddit") or {}
    if rcfg.get("client_id") and rcfg.get("client_secret"):
        reddit.configure(rcfg["client_id"], rcfg["client_secret"],
                         rcfg.get("user_agent", ""))

    base = expand(cfg.get("queries") or [])
    extra = expand(cfg.get("site_queries") or [])

    # ambil sebagian kueri per putaran, bergiliran, supaya tiap run cepat
    cap = int(cfg.get("max_queries", 6))
    if cap and len(base) > cap:
        start = (run_id * cap) % len(base)
        rot = (base + base)[start:start + cap]
    else:
        rot = base
    queries = list(rot) + extra
    engines = cfg["engine"] if isinstance(cfg["engine"], list) else [cfg["engine"]]
    engines = [e for e in engines if e in search.ENGINES]
    if "reddit" in engines and not reddit.configured():
        engines.remove("reddit")
    raw: list[dict] = []

    if engines:
        raw += search.run_queries(queries, engines, delay=delay, errors=errors)

    # subreddit langsung lewat OAuth: /new menampilkan 100 pos terakhir
    # subreddit: OAuth kalau ada kredensial, kalau tidak pakai /new/.rss
    subs = cfg.get("subreddits") or []
    if reddit.configured():
        for sub in subs:
            try:
                items = reddit.listing(sub, limit=100)
                for it in items:
                    it["source"] = f"reddit:r/{sub}"
                raw.extend(items)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"reddit:r/{sub}:{exc}")
            time.sleep(2)
    else:
        for sub in subs:
            try:
                items = search.search_rss(f"https://www.reddit.com/r/{sub}/new/.rss?limit=100")
                for it in items:
                    it["source"] = f"reddit:r/{sub}"
                raw.extend(items)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"rss:r/{sub}:{exc}")

    # forum Discourse / komunitas: pakai filter after: supaya server yang menyaring
    if not cfg.get("_fast"):
        after = (dt.datetime.now() - dt.timedelta(hours=int(cfg.get("max_age_hours", 24)))
                 ).strftime("%Y-%m-%d")
        for base in cfg.get("forums") or []:
            host = base.split("//")[-1].split("/")[0]
            for q in (cfg.get("community_queries") or [])[:3]:
                try:
                    items = search.search_discourse(base, q, after=after)
                    for it in items:
                        it["source"] = f"forum:{host}"
                    raw.extend(items)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"forum:{host}:{exc}")
                time.sleep(1.5)

    for feed in cfg.get("feeds") or []:
        try:
            items = search.search_rss(feed["url"])
            for it in items:
                it["source"] = f"rss:{feed['name']}"
            raw += items
        except Exception as exc:  # noqa: BLE001
            errors.append(f"rss:{feed.get('name')}:{exc}")
        time.sleep(delay[0])

    # dedupe kasar sebelum ambil halaman
    seen: set[str] = set()
    uniq: list[dict] = []
    for it in raw:
        key = search.domain_of(it["url"]) + it["title"].strip().lower()
        if key in seen or not it.get("url"):
            continue
        seen.add(key)
        uniq.append(it)

    cutoff = int(time.time()) - int(cfg.get("max_age_hours", 24)) * 3600
    undated: list[str] = []
    findings: list[Finding] = []
    for it in uniq:
        domain = search.domain_of(it["url"])
        text = f"{it['title']} {it['snippet']}"
        if not extract.is_relevant(it["title"], it["snippet"], it["url"]):
            continue
        pub = it.get("published")
        if pub is None:
            undated.append(it["url"])
            continue
        if pub < cutoff:
            continue
        codes = extract.extract_codes(text)
        if not extract.is_offer(it["title"], it["snippet"], codes):
            continue
        brand = extract.detect_brand(text + " " + it["url"])
        score = extract.score_finding(it["title"], it["snippet"], it["url"],
                                      domain, codes, trust, it.get("source", ""))
        findings.append(Finding(
            url=it["url"], domain=domain, title=it["title"],
            snippet=it["snippet"], source=it.get("source", ""),
            brand=brand, codes=codes, score=score,
            expiry=extract.guess_expiry(text + " " + it["url"]),
            published=pub,
            raw={"query": it.get("query", "")},
        ))
    if undated:
        errors.append(f"{len(undated)} hasil tanpa tanggal dibuang (jendela 24 jam)")
    return findings, errors


def deep_scan(cfg: dict, findings: list[Finding]) -> None:
    """Buka halaman yang skornya menjanjikan tapi belum ada kode, cari lebih dalam."""
    workers = int(cfg["rate"].get("workers", 3))
    targets = [f for f in findings if not f.codes and f.score >= 20][:25]

    def work(f: Finding) -> None:
        page = search.fetch_page(f.url)
        if not page:
            return
        codes = extract.extract_codes(page)
        if codes:
            f.codes = codes
            trust = {k.lower(): v for k, v in (cfg.get("trust") or {}).items()}
            f.score = extract.score_finding(f.title, f.snippet + " " + page[:2000],
                                            f.url, f.domain, codes, trust)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, targets))


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_cfg(args.config)
    cfg["_fast"] = bool(args.fast)
    if args.fast:
        # mode cepat untuk cron rapat: 2 kueri, tanpa subreddit/forum, tanpa buka halaman
        cfg["max_queries"] = 2
        cfg["subreddits"] = []
        args.deep = False
    store = Store(cfg["store"]["db"])
    run_id = store.start_run()

    t0 = time.time()
    findings, errors = harvest(cfg, run_id=run_id)
    if args.deep:
        deep_scan(cfg, findings)

    min_keep = int(cfg["score"]["min_keep"])
    kept = [f for f in findings if f.score >= min_keep]

    new_items = 0
    for f in kept:
        if store.upsert(f):
            new_items += 1

    pending = store.pending_notify(int(cfg["score"]["min_notify"]),
                                   int(cfg["score"].get("min_notify_coded", 30)))
    if pending and not args.dry:
        n = cfg.get("notify") or {}
        sent = False
        if n.get("discord_webhook"):
            sent = notify.send_discord(n["discord_webhook"], pending) or sent
        if n.get("telegram_token"):
            chat = n.get("telegram_chat") or store.get_setting("telegram_chat")
            if not chat:
                chat = notify.resolve_chat(n["telegram_token"]) or ""
                if chat:
                    store.set_setting("telegram_chat", chat)
                    print(f"[pantau] chat_id tersimpan: {chat}")
            sent = notify.send_telegram(n["telegram_token"], chat, pending) or sent
        if sent:
            store.mark_notified([p["uid"] for p in pending])
            print(f"[pantau] telegram: {len(pending)} temuan terkirim")
        else:
            print(f"[pantau] telegram: {len(pending)} temuan menunggu, kirim gagal")

    store.finish_run(run_id, len(cfg.get("queries") or []), len(findings),
                     new_items, errors)

    print(f"[pantau] putaran #{run_id} · {len(findings)} temuan · "
          f"{len(kept)} lolos filter · {new_items} baru · "
          f"{time.time() - t0:.1f}s")
    for e in errors[:5]:
        print(f"  ! {e}", file=sys.stderr)

    if args.show:
        for row in store.top(limit=args.limit, min_score=min_keep,
                             order="new" if args.new else "score"):
            codes = json.loads(row["codes"] or "[]")
            print(f"\n[{row['score']:3d}] {row['title'][:90]}")
            print(f"      {row['domain']}  ·  {row['source']}")
            if codes:
                print(f"      kode: {', '.join(codes)}")
            print(f"      {row['url']}")
    return 0


def cmd_codes(args: argparse.Namespace) -> int:
    cfg = load_cfg(args.config)
    store = Store(cfg["store"]["db"])
    since = int(time.time()) - args.days * 86400
    rows = store.fresh_codes(since, limit=args.limit)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("belum ada kode baru.")
        return 0
    print(f"{'KODE':<24} {'MEREK':<12} SKOR  SUMBER")
    print("-" * 78)
    for r in rows:
        seen = dt.datetime.fromtimestamp(r["first_seen"]).strftime("%d/%m %H:%M")
        print(f"{r['code']:<22} {(r['brand'] or '-'):<12} {r['score']:<4} {seen}  {r['url'][:38]}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    cfg = load_cfg(args.config)
    store = Store(cfg["store"]["db"])
    out_dir = cfg["store"]["export_dir"]
    os.makedirs(out_dir, exist_ok=True)
    rows = store.top(limit=args.limit, min_score=int(cfg["score"]["min_keep"]))
    if args.days:
        cutoff = int(time.time()) - args.days * 86400
        rows = [r for r in rows if (r.get("published") or r["first_seen"]) >= cutoff]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    json_path = os.path.join(out_dir, f"pantau-{stamp}.json")
    csv_path = os.path.join(out_dir, f"pantau-{stamp}.csv")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write("score,brand,codes,title,url,domain\n")
        for r in rows:
            codes = "|".join(json.loads(r["codes"] or "[]"))
            title = r["title"].replace('"', "'")
            fh.write(f'{r["score"]},{r["brand"]},"{codes}","{title}",{r["url"]},{r["domain"]}\n')
    print(f"tersimpan: {json_path}\n           {csv_path}  ({len(rows)} baris)")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    cfg = load_cfg(args.config)
    store = Store(cfg["store"]["db"])
    s = store.stats()
    print(f"total temuan  : {s['findings']}")
    print(f"kode unik     : {s['unique_codes']}")
    last = s.get("last_run")
    if last:
        when = dt.datetime.fromtimestamp(last["started"]).strftime("%d/%m %H:%M")
        print(f"putaran akhir : #{last['id']} · {when} · {last['new_items']} baru")
        errs = json.loads(last.get("errors") or "[]")
        if errs:
            print(f"galat         : {len(errs)} (lihat DB)")
    return 0


def cmd_telegram(args: argparse.Namespace) -> int:
    cfg = load_cfg(args.config)
    n = cfg.get("notify") or {}
    token = n.get("telegram_token") or ""
    if not token:
        print("TELEGRAM_TOKEN kosong — isi di .env", file=sys.stderr)
        return 2
    info = notify.bot_info(token)
    if not info.get("ok"):
        print(f"token ditolak Telegram: {info.get('error') or info}", file=sys.stderr)
        return 2
    bot = info["result"]
    print(f"bot: @{bot['username']} ({bot['first_name']})")

    chat = n.get("telegram_chat") or ""
    if not chat or args.wait:
        print("menunggu pesan masuk… kirim /start ke bot itu sekarang")
        chat = notify.resolve_chat(token, timeout_s=args.wait) or ""
        if not chat:
            print("belum ada chat_id. kirim /start dulu, lalu ulangi.", file=sys.stderr)
            return 2
    print(f"chat_id: {chat}")

    store = Store(cfg["store"]["db"])
    pending = store.pending_notify(int(cfg["score"]["min_notify"]),
                                   int(cfg["score"].get("min_notify_coded", 30)))
    if pending:
        ok = notify.send_telegram(token, chat, pending)
        print(f"terkirim {len(pending)} temuan" if ok else "gagal kirim")
    else:
        ok = notify.send_plain(token, chat,
                               "pantau aktif. belum ada temuan di atas ambang skor.")
        print("tes pesan terkirim" if ok else "gagal kirim tes")
    if ok and chat:
        print(f'\nok. simpan ini di .env:\nTELEGRAM_CHAT={chat}')
    return 0 if ok else 1


def cmd_reddit(args: argparse.Namespace) -> int:
    cfg = load_cfg(args.config)
    r = cfg.get("reddit") or {}
    reddit.configure(r.get("client_id", ""), r.get("client_secret", ""),
                     r.get("user_agent", ""))
    if not reddit.configured():
        print("REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET belum ada di .env", file=sys.stderr)
        return 2
    try:
        info = reddit.check()
    except Exception as exc:  # noqa: BLE001
        print(f"gagal: {exc}", file=sys.stderr)
        return 1
    print(f"token  : {info['token']}")
    print(f"akses  : r/{info['subreddit']} ({info['subscribers']:,} anggota)")
    posts = reddit.listing("ClaudeAI", limit=5)
    print(f"listing: {len(posts)} pos terbaru, contoh: {posts[0]['title'][:60] if posts else '-'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pantau", description="pelacak kode promo / voucher AI")
    p.add_argument("-c", "--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="jalankan satu putaran")
    r.add_argument("--deep", action="store_true", help="buka halaman untuk cari kode di dalam")
    r.add_argument("--show", action="store_true", help="cetak hasil teratas")
    r.add_argument("--dry", action="store_true", help="jangan kirim notifikasi")
    r.add_argument("--limit", type=int, default=20)
    r.add_argument("--new", action="store_true", help="urutkan dari yang paling baru")
    r.add_argument("--fast", action="store_true",
                   help="mode ringan untuk cron rapat: 2 kueri, tanpa subreddit")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("codes", help="daftar kode baru")
    c.add_argument("--days", type=int, default=7)
    c.add_argument("--limit", type=int, default=100)
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_codes)

    e = sub.add_parser("export", help="ekspor JSON + CSV")
    e.add_argument("--limit", type=int, default=200)
    e.add_argument("--days", type=int, default=3, help="hanya N hari terakhir (0 = semua)")
    e.set_defaults(func=cmd_export)

    s = sub.add_parser("stats", help="ringkasan DB")
    s.set_defaults(func=cmd_stats)

    rd = sub.add_parser("reddit-check", help="validasi kredensial OAuth Reddit")
    rd.set_defaults(func=cmd_reddit)

    tg = sub.add_parser("telegram", help="cek bot + cari chat_id + tes kirim")
    tg.add_argument("--wait", type=int, default=0,
                    help="detik menunggu pesan /start masuk")
    tg.set_defaults(func=cmd_telegram)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())