"""server.py — panel web kecil buat lihat dan cari hasil pantauan.

Jalankan: python -m pantau.server --config config.yaml --port 8000
Buka   : http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import yaml

PAGE = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>pantau · kode promo AI</title>
<style>
 :root{--bg:#0d0f10;--fg:#e8e6e3;--dim:#7a7f85;--line:#1f2427;--hi:#9ef01a}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--fg);
      font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
 header{padding:18px 22px;border-bottom:1px solid var(--line);
        display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
 h1{font-size:15px;margin:0;letter-spacing:.14em;text-transform:uppercase}
 .stat{color:var(--dim)}
 .stat b{color:var(--hi)}
 form{padding:14px 22px;border-bottom:1px solid var(--line);display:flex;gap:10px}
 input{background:#121619;border:1px solid var(--line);color:var(--fg);
       padding:8px 11px;border-radius:3px;font:inherit;flex:1;min-width:0}
 button{background:var(--hi);color:#0d0f10;border:0;padding:8px 16px;
        border-radius:3px;font:inherit;font-weight:700;cursor:pointer}
 table{width:100%;border-collapse:collapse}
 td,th{padding:10px 22px;border-bottom:1px solid var(--line);text-align:left;
       vertical-align:top;font-size:13px}
 th{color:var(--dim);font-weight:400;font-size:11px;letter-spacing:.12em;
    text-transform:uppercase}
 .score{font-weight:700;font-variant-numeric:tabular-nums}
 .s-hi{color:var(--hi)} .s-mid{color:#ffd166} .s-lo{color:var(--dim)}
 .codes{display:flex;gap:6px;flex-wrap:wrap;margin-top:5px}
 code{background:#121619;border:1px solid #2a3237;padding:1px 6px;
      border-radius:3px;color:var(--hi);font-size:12px}
 a{color:var(--fg);text-decoration:none;border-bottom:1px solid #333}
 a:hover{border-color:var(--hi)}
 .meta{color:var(--dim);font-size:11px;margin-top:4px}
 .empty{padding:60px 22px;color:var(--dim);text-align:center}
</style></head><body>
<header>
  <h1>pantau</h1>
  <span class="stat"><b>__FINDINGS__</b> temuan</span>
  <span class="stat"><b>__CODES__</b> kode unik</span>
  <span class="stat">__WHEN__</span>
</header>
<form method="get">
  <input name="q" value="__Q__" placeholder="cari merek, judul, atau kode…">
  <input name="min" value="__MIN__" style="flex:0 0 90px" placeholder="skor min">
  <button>CARI</button>
</form>
<table>
<thead><tr><th style="width:56px">skor</th><th>temuan</th><th style="width:110px">sumber</th></tr></thead>
<tbody>__ROWS__</tbody>
</table>
</body></html>"""

ROW = """<tr>
 <td class="score {cls}">{score}</td>
 <td><a href="{url}" target="_blank" rel="noopener">{title}</a>
   <div class="codes">{codes}</div>
   <div class="meta">{domain} · terlihat {seen}</div></td>
 <td class="meta">{source}</td>
</tr>"""


def render(cfg: dict, q: str, min_score: int, limit: int = 200) -> str:
    store_path = cfg["store"]["db"]
    conn = sqlite3.connect(store_path)
    conn.row_factory = sqlite3.Row
    where, args = ["score >= ?"], [min_score]
    if q:
        where.append("(title LIKE ? OR brand LIKE ? OR codes LIKE ? OR url LIKE ?)")
        args += [f"%__Q__%"] * 4
    sql = ("SELECT * FROM findings WHERE " + " AND ".join(where) +
           " ORDER BY score DESC, last_seen DESC LIMIT ?")
    rows = conn.execute(sql, args + [limit]).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    uniq = conn.execute("SELECT COUNT(DISTINCT code) FROM codes").fetchone()[0]
    last = conn.execute("SELECT MAX(last_seen) FROM findings").fetchone()[0]
    conn.close()

    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    body = []
    for r in rows:
        codes = json.loads(r["codes"] or "[]")
        cls = "s-hi" if r["score"] >= 45 else ("s-mid" if r["score"] >= 20 else "s-lo")
        seen = dt.datetime.fromtimestamp(r["last_seen"]).strftime("%d/%m %H:%M") if r["last_seen"] else "-"
        body.append(ROW.format(
            score=r["score"], cls=cls, url=esc(r["url"]), title=esc(r["title"]),
            codes="".join(f"<code>{esc(c)}</code>" for c in codes),
            domain=esc(r["domain"]), seen=seen, source=esc(r["source"]),
        ))
    when = dt.datetime.fromtimestamp(last).strftime("terakhir %d/%m %H:%M") if last else "belum ada putaran"
    out = PAGE
    for key, val in (("__FINDINGS__", total), ("__CODES__", uniq), ("__WHEN__", when),
                     ("__Q__", esc(q)), ("__MIN__", min_score),
                     ("__ROWS__", "\n".join(body) or
                      '<tr><td colspan="3" class="empty">kosong</td></tr>')):
        out = out.replace(key, str(val))
    return out


def make_handler(cfg: dict, allow_run: bool):
    config_path = cfg.get("_path", "config.yaml")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # senyap
            pass

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/run" and allow_run:
                subprocess.Popen([sys.executable, "-m", "pantau.cli", "run",
                                  "-c", config_path, "--deep"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.send_response(303)
                self.send_header("Location", "/")
                self.end_headers()
                return
            qs = parse_qs(parsed.query)
            q = (qs.get("q") or [""])[0][:80]
            try:
                min_score = int((qs.get("min") or ["6"])[0])
            except ValueError:
                min_score = 6
            html_out = render(cfg, q, min_score).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_out)))
            self.end_headers()
            self.wfile.write(html_out)

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--allow-run", action="store_true",
                    help="izinkan tombol /run memicu putaran baru")
    a = ap.parse_args()
    with open(a.config, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg["_path"] = a.config
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(cfg, a.allow_run))
    print(f"pantau di http://{a.host}:{a.port}  (ctrl-c berhenti)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())