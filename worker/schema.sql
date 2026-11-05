CREATE TABLE IF NOT EXISTS findings (
  uid        TEXT PRIMARY KEY,
  url        TEXT NOT NULL,
  domain     TEXT NOT NULL DEFAULT '',
  title      TEXT NOT NULL,
  snippet    TEXT NOT NULL DEFAULT '',
  source     TEXT NOT NULL DEFAULT '',
  brand      TEXT NOT NULL DEFAULT '',
  codes      TEXT NOT NULL DEFAULT '[]',
  score      INTEGER NOT NULL DEFAULT 0,
  expiry     TEXT,
  first_seen INTEGER NOT NULL,
  last_seen  INTEGER NOT NULL,
  notified   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_findings_score ON findings(score DESC, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_findings_brand ON findings(brand);

CREATE TABLE IF NOT EXISTS codes (
  code       TEXT NOT NULL,
  brand      TEXT NOT NULL DEFAULT '',
  uid        TEXT NOT NULL,
  first_seen INTEGER NOT NULL,
  PRIMARY KEY (code, uid)
);
