"""pantau.db — simpanan hasil, dedupe, riwayat harga/promo."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Iterator, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    uid           TEXT PRIMARY KEY,
    url           TEXT NOT NULL,
    domain        TEXT NOT NULL,
    title         TEXT NOT NULL,
    snippet       TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL,           -- ddg / bing / reddit / rss ...
    brand         TEXT NOT NULL DEFAULT '',
    codes         TEXT NOT NULL DEFAULT '[]',   -- JSON list
    score         INTEGER NOT NULL DEFAULT 0,
    first_seen    INTEGER NOT NULL,
    last_seen     INTEGER NOT NULL,
    notified      INTEGER NOT NULL DEFAULT 0,
    expiry        TEXT,
    raw           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_findings_score  ON findings(score DESC, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_findings_brand  ON findings(brand, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_findings_notify ON findings(notified) WHERE notified = 0;

CREATE TABLE IF NOT EXISTS codes (
    code       TEXT NOT NULL,
    brand      TEXT NOT NULL DEFAULT '',
    uid        TEXT NOT NULL,
    first_seen INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL,
    PRIMARY KEY (code, uid)
);
CREATE INDEX IF NOT EXISTS idx_codes_seen ON codes(first_seen DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started   INTEGER NOT NULL,
    finished  INTEGER,
    queries   INTEGER NOT NULL DEFAULT 0,
    found     INTEGER NOT NULL DEFAULT 0,
    new_items INTEGER NOT NULL DEFAULT 0,
    errors    TEXT NOT NULL DEFAULT '[]'
);
"""


@dataclass
class Finding:
    url: str
    domain: str
    title: str
    snippet: str = ""
    source: str = ""
    brand: str = ""
    codes: list[str] = field(default_factory=list)
    score: int = 0
    expiry: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        key = normalize_url(self.url) + "|" + self.title.strip().lower()
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    def as_row(self) -> dict:
        d = asdict(self)
        d["codes"] = json.dumps(self.codes, ensure_ascii=False)
        d["raw"] = json.dumps(self.raw, ensure_ascii=False)
        d["uid"] = self.uid
        return d


def normalize_url(url: str) -> str:
    url = url.split("#", 1)[0]
    for junk in ("&utm_", "?utm_"):
        if junk in url:
            url = url.split(junk, 1)[0]
    return url.rstrip("/").lower()


class Store:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(findings)")}
            if "expiry" not in cols:
                c.execute("ALTER TABLE findings ADD COLUMN expiry TEXT")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---------- tulis ----------

    def upsert(self, f: Finding) -> bool:
        """Simpan satu temuan. True kalau ini barang baru."""
        row = f.as_row()
        now = int(time.time())
        with self._conn() as c:
            cur = c.execute("SELECT first_seen FROM findings WHERE uid = ?", (row["uid"],))
            existing = cur.fetchone()
            if existing:
                c.execute(
                    "UPDATE findings SET last_seen=?, score=?, codes=?, snippet=?, "
                    "expiry=?, raw=? WHERE uid=?",
                    (now, f.score, row["codes"], f.snippet, f.expiry, row["raw"], row["uid"]),
                )
                is_new = False
            else:
                c.execute(
                    """INSERT INTO findings
                       (uid,url,domain,title,snippet,source,brand,codes,score,
                        first_seen,last_seen,notified,expiry,raw)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?)""",
                    (row["uid"], f.url, f.domain, f.title, f.snippet, f.source,
                     f.brand, row["codes"], f.score, now, now, f.expiry, row["raw"]),
                )
                is_new = True
            for code in f.codes:
                c.execute(
                    """INSERT INTO codes (code,brand,uid,first_seen,last_seen)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(code,uid) DO UPDATE SET last_seen=excluded.last_seen""",
                    (code, f.brand, row["uid"], now, now),
                )
        return is_new

    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO settings (key,value) VALUES (?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, value))

    def start_run(self) -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO runs (started) VALUES (?)", (int(time.time()),))
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, queries: int, found: int, new_items: int, errors: list[str]) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE runs SET finished=?, queries=?, found=?, new_items=?, errors=? WHERE id=?",
                (int(time.time()), queries, found, new_items,
                 json.dumps(errors, ensure_ascii=False), run_id),
            )

    def mark_notified(self, uids: Iterable[str]) -> None:
        with self._conn() as c:
            c.executemany("UPDATE findings SET notified=1 WHERE uid=?", [(u,) for u in uids])

    # ---------- baca ----------

    def top(self, limit: int = 50, min_score: int = 0, brand: str | None = None) -> list[dict]:
        q = "SELECT * FROM findings WHERE score >= ?"
        args: list = [min_score]
        if brand:
            q += " AND brand = ?"
            args.append(brand)
        q += " ORDER BY score DESC, last_seen DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args)]

    def fresh_codes(self, since_ts: int, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT c.code, c.brand, c.first_seen, f.url, f.title, f.score
                   FROM codes c JOIN findings f ON f.uid = c.uid
                   WHERE c.first_seen >= ?
                   ORDER BY f.score DESC, c.first_seen DESC LIMIT ?""",
                (since_ts, limit),
            )
            return [dict(r) for r in rows]

    def pending_notify(self, min_score: int, min_coded: int = 999) -> list[dict]:
        """Temuan yang belum dilaporkan: skor tinggi, atau ada kode konkret."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM findings WHERE notified=0 "
                "AND (score >= ? OR (codes != '[]' AND score >= ?)) "
                "ORDER BY score DESC, last_seen DESC LIMIT 25",
                (min_score, min_coded),
            )
            return [dict(r) for r in rows]

    def stats(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
            codes = c.execute("SELECT COUNT(DISTINCT code) FROM codes").fetchone()[0]
            last = c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            return {"findings": total, "unique_codes": codes,
                    "last_run": dict(last) if last else None}