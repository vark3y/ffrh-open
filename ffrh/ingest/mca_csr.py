"""Ingest the North East slice of the National CSR Portal project ledger."""
from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from pathlib import Path

from ..config import MCA_CSR_CSV, NE_STATES
from ..sources import MCA_CSR
from .themes import classify_subarea, sector_to_theme

csv.field_size_limit(10**9)

NE_ROCS = {"ROC-SHILLONG", "ROC-GUWAHATI"}


def _impl_mode(raw: str) -> str:
    r = (raw or "").strip().lower()
    if "agenc" in r:
        return "agency"
    if "direct" in r:
        return "direct"
    return "unstated"


def _f(x: str) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def ingest(con: sqlite3.Connection, path: Path = MCA_CSR_CSV) -> dict:
    con.execute("DELETE FROM csr_projects WHERE source_id=?", (MCA_CSR.source_id,))
    con.execute("DELETE FROM funders WHERE source_id=?", (MCA_CSR.source_id,))
    funders: dict[str, tuple[str, str]] = {}
    rows = []
    unmapped = Counter()
    nat = {}  # fy -> [national_cr, ne_cr, set(cins)]
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for i, r in enumerate(reader, start=2):  # header is row 1
            state = (r.get("state") or "").strip().upper()
            fy = r.get("fiscal_year")
            spent = _f(r.get("amount_spent"))
            agg = nat.setdefault(fy, [0.0, 0.0, set()])
            agg[0] += spent; agg[2].add(r.get("cin"))
            if state not in NE_STATES:
                continue
            agg[1] += spent
            cin = (r.get("cin") or "").strip()
            if not cin:
                continue
            name = (r.get("company_name") or "").strip()
            roc = (r.get("roc") or "").strip().upper()
            funders.setdefault(cin, (name, roc))
            sector = (r.get("sector") or "").strip()
            theme = sector_to_theme(sector)
            if theme == "other" and sector:
                unmapped[sector] += 1
            subarea, rule = classify_subarea(r.get("csr_project_name") or "")
            rows.append((
                cin, r.get("fiscal_year"), state, NE_STATES[state],
                (r.get("district_as_per_lgd") or r.get("district_as_per_source") or "").strip() or None,
                (r.get("district_lgd_code") or "").strip() or None,
                (r.get("csr_project_name") or "").strip() or None,
                sector or None, theme, subarea, rule, _impl_mode(r.get("implementation_mode")),
                _f(r.get("project_amount_outlay")), _f(r.get("amount_spent")),
                MCA_CSR.source_id, i,
            ))
    con.executemany(
        "INSERT INTO funders(cin,name,roc,is_ne_registered,source_id) VALUES(?,?,?,?,?)",
        [(cin, n, roc, int(roc in NE_ROCS), MCA_CSR.source_id) for cin, (n, roc) in funders.items()],
    )
    con.executemany(
        """INSERT INTO csr_projects(cin,fy,state,state_code,district,district_lgd,project_name,sector,theme,
           subarea,subarea_rule,impl_mode,outlay_cr,spent_cr,source_id,source_row)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    con.execute("DELETE FROM national_totals")
    con.executemany("INSERT INTO national_totals(fy,national_cr,ne_cr,national_companies,source_id) VALUES(?,?,?,?,?)",
                    [(fy, round(a[0], 4), round(a[1], 4), len(a[2]), MCA_CSR.source_id) for fy, a in nat.items() if fy])
    con.commit()
    return {"funders": len(funders), "projects": len(rows), "unmapped_sectors": unmapped.most_common(20)}
