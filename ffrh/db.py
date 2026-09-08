"""SQLite access + schema. One file, no ORM, so anyone can open it with the sqlite3 CLI."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
-- ---------------------------------------------------------------- provenance
-- Every fact table below carries a source_id. Nothing is shown to a user without
-- the source name, URL and the date we retrieved it.
CREATE TABLE IF NOT EXISTS sources (
  source_id     TEXT PRIMARY KEY,           -- short slug, e.g. mca_csr_portal_2014_24
  name          TEXT NOT NULL,
  publisher     TEXT NOT NULL,
  url           TEXT NOT NULL,
  licence       TEXT,                       -- as stated by the publisher, or 'unstated'
  retrieved_at  TEXT NOT NULL,              -- ISO date the copy we hold was retrieved
  covers        TEXT,                       -- period the data covers
  notes         TEXT,
  personal_data TEXT                        -- 'none' | description of personal data present
);

-- ---------------------------------------------------------------- funder side (open)
CREATE TABLE IF NOT EXISTS funders (
  cin           TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  roc           TEXT,
  is_ne_registered INTEGER NOT NULL DEFAULT 0,  -- ROC-Shillong / Guwahati registration
  source_id     TEXT NOT NULL REFERENCES sources(source_id)
);

CREATE TABLE IF NOT EXISTS csr_projects (
  project_id    INTEGER PRIMARY KEY,
  cin           TEXT NOT NULL REFERENCES funders(cin),
  fy            TEXT NOT NULL,                -- '2023-24'
  state         TEXT NOT NULL,                -- upper-case, as in source
  state_code    TEXT NOT NULL,
  district      TEXT,                         -- district_as_per_lgd
  district_lgd  TEXT,
  project_name  TEXT,
  sector        TEXT,                         -- Schedule VII label as in source
  theme         TEXT,                         -- our coarse theme (see ingest/themes.py)
  subarea       TEXT,                         -- livelihood sub-area, keyword-derived, or NULL
  subarea_rule  TEXT,                         -- which keyword fired (traceability)
  impl_mode     TEXT,                         -- 'agency' | 'direct' | 'unstated'
  outlay_cr     REAL,                         -- unreliable column; kept, never used for scoring
  spent_cr      REAL NOT NULL,                -- INR crore
  source_id     TEXT NOT NULL REFERENCES sources(source_id),
  source_row    INTEGER                       -- 1-based row number in the raw CSV
);
CREATE INDEX IF NOT EXISTS ix_proj_cin ON csr_projects(cin);
CREATE INDEX IF NOT EXISTS ix_proj_state_theme ON csr_projects(state_code, theme);
CREATE INDEX IF NOT EXISTS ix_proj_fy ON csr_projects(fy);

-- National context so NE numbers can be shown as a share, with the same source.
CREATE TABLE IF NOT EXISTS national_totals (
  fy            TEXT PRIMARY KEY,
  national_cr   REAL NOT NULL,
  ne_cr         REAL NOT NULL,
  national_companies INTEGER NOT NULL,
  source_id     TEXT NOT NULL REFERENCES sources(source_id)
);

-- ---------------------------------------------------------------- NGO side (open, PII stripped)
CREATE TABLE IF NOT EXISTS ngos (
  darpan_id     TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  state         TEXT NOT NULL,
  state_code    TEXT NOT NULL,
  city          TEXT,
  source_id     TEXT NOT NULL REFERENCES sources(source_id)
);
CREATE TABLE IF NOT EXISTS ngo_grants (
  grant_id      INTEGER PRIMARY KEY,
  darpan_id     TEXT NOT NULL REFERENCES ngos(darpan_id),
  source_of_funds TEXT,
  funding_agency  TEXT,
  field_of_work   TEXT,
  theme           TEXT,                       -- derived, NULL when field_of_work is junk
  from_date       TEXT,
  to_date         TEXT,
  amount_inr      REAL,
  source_id       TEXT NOT NULL REFERENCES sources(source_id),
  source_row      INTEGER
);
CREATE INDEX IF NOT EXISTS ix_grants_ngo ON ngo_grants(darpan_id);

-- ---------------------------------------------------------------- signals (open)
CREATE TABLE IF NOT EXISTS narrative_items (
  item_id       INTEGER PRIMARY KEY,
  source_id     TEXT NOT NULL REFERENCES sources(source_id),
  url           TEXT NOT NULL UNIQUE,
  title         TEXT NOT NULL,
  published_at  TEXT,
  retrieved_at  TEXT NOT NULL,
  summary       TEXT,
  signal_type   TEXT NOT NULL,                -- 'funding' | 'narrative'
  funder_cins   TEXT,                         -- JSON list of CINs matched by name
  states        TEXT,                         -- JSON list of state codes mentioned
  themes        TEXT,                         -- JSON list of themes mentioned
  entry_kind    TEXT NOT NULL DEFAULT 'auto'  -- 'auto' (feed) | 'manual' (logged by a person, with URL)
);

CREATE TABLE IF NOT EXISTS rfps (
  rfp_id        INTEGER PRIMARY KEY,
  title         TEXT NOT NULL,
  issuer        TEXT,
  issuer_cin    TEXT,
  url           TEXT NOT NULL UNIQUE,
  deadline      TEXT,
  states        TEXT,                         -- JSON list; empty = national
  themes        TEXT,                         -- JSON list
  body_text     TEXT,                         -- public text as retrieved
  retrieved_at  TEXT NOT NULL,
  source_id     TEXT NOT NULL REFERENCES sources(source_id),
  status        TEXT NOT NULL DEFAULT 'open'
);

-- ---------------------------------------------------------------- protected layer
-- CSO profiles are hub-specific. Each non-public field group records its consent basis.
CREATE TABLE IF NOT EXISTS cso_profiles (
  cso_id        TEXT PRIMARY KEY,
  darpan_id     TEXT REFERENCES ngos(darpan_id),
  display_name  TEXT NOT NULL,
  is_stand_in   INTEGER NOT NULL DEFAULT 0,   -- 1 = built from public register only, not an FFRH cohort member
  state_code    TEXT NOT NULL,
  districts     TEXT,                         -- JSON list
  themes        TEXT NOT NULL,                -- JSON list of our themes
  subareas      TEXT,                         -- JSON list of livelihood sub-areas
  programme_summary TEXT,
  ask_min_lakh  REAL,
  ask_max_lakh  REAL,
  fields_json   TEXT NOT NULL DEFAULT '{}',   -- {field: {value, source_id, retrieved_at, consent_basis, visibility}}
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
  draft_id      INTEGER PRIMARY KEY,
  cso_id        TEXT NOT NULL REFERENCES cso_profiles(cso_id),
  rfp_id        INTEGER REFERENCES rfps(rfp_id),
  funder_cin    TEXT,
  mode          TEXT NOT NULL,                -- 'model' | 'template'
  model         TEXT,
  created_at    TEXT NOT NULL,
  draft_json    TEXT NOT NULL,                -- sections -> paragraphs -> {text, source_ids, kind}
  dropped_json  TEXT                          -- paragraphs removed for lacking a valid source
);

CREATE TABLE IF NOT EXISTS access_log (
  id            INTEGER PRIMARY KEY,
  at            TEXT NOT NULL,
  persona       TEXT NOT NULL,
  path          TEXT NOT NULL,
  cso_id        TEXT
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.commit()


@contextmanager
def session(path: Path | None = None):
    con = connect(path)
    try:
        yield con
        con.commit()
    finally:
        con.close()
