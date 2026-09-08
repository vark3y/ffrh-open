"""Ingest the North East slice of NGO Darpan. Emails are read and discarded, never stored."""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from ..config import NE_STATES, NGO_DARPAN_CSV
from ..sources import NGO_DARPAN
from .themes import darpan_theme

csv.field_size_limit(10**9)


def _amt(x: str) -> float | None:
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def ingest(con: sqlite3.Connection, path: Path = NGO_DARPAN_CSV) -> dict:
    con.execute("DELETE FROM cso_profiles WHERE is_stand_in=1")  # rebuilt by cohort.build()
    con.execute("DELETE FROM ngo_grants WHERE source_id=?", (NGO_DARPAN.source_id,))
    con.execute("DELETE FROM ngos WHERE source_id=?", (NGO_DARPAN.source_id,))
    ngos: dict[str, tuple] = {}
    grants = []
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for i, r in enumerate(reader, start=2):
            state = (r.get("state_of_registration") or "").strip().upper()
            if state not in NE_STATES:
                continue
            uid = (r.get("unique_id") or "").strip()
            if not uid:
                continue
            ngos.setdefault(uid, ((r.get("ngo_name") or "").strip(), state, NE_STATES[state],
                                  (r.get("city_of_registration") or "").strip() or None))
            fow = (r.get("field_of_work") or "").strip()
            grants.append((uid, (r.get("source_of_funds") or "").strip() or None,
                           (r.get("funding_agency") or "").strip() or None,
                           fow or None, darpan_theme(fow),
                           r.get("from_date") or None, r.get("to_date") or None,
                           _amt(r.get("amount_sanctioned")), NGO_DARPAN.source_id, i))
    con.executemany("INSERT INTO ngos(darpan_id,name,state,state_code,city,source_id) VALUES(?,?,?,?,?,?)",
                    [(uid, n, s, sc, c, NGO_DARPAN.source_id) for uid, (n, s, sc, c) in ngos.items()])
    con.executemany("""INSERT INTO ngo_grants(darpan_id,source_of_funds,funding_agency,field_of_work,theme,
                       from_date,to_date,amount_inr,source_id,source_row) VALUES(?,?,?,?,?,?,?,?,?,?)""", grants)
    con.commit()
    themed = con.execute("SELECT COUNT(*) FROM ngo_grants WHERE theme IS NOT NULL").fetchone()[0]
    return {"ngos": len(ngos), "grant_rows": len(grants), "grant_rows_with_theme": themed}
