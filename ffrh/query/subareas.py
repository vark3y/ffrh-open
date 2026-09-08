"""Which livelihood sub-areas do North East CSR funders actually put money into?"""
from __future__ import annotations

import sqlite3

from ..ingest.themes import LIVELIHOOD_FAMILY, SUBAREA_LABELS
from ..sources import MCA_CSR
from . import evidence as ev


def attractiveness(con: sqlite3.Connection, state_code: str | None = None) -> dict:
    fam = ",".join(f"'{t}'" for t in LIVELIHOOD_FAMILY)
    w, args = "", []
    if state_code:
        w, args = " AND state_code=?", [state_code]
    rows = con.execute(f"""
        SELECT subarea, fy, ROUND(SUM(spent_cr),3) cr, COUNT(*) n, COUNT(DISTINCT cin) funders
        FROM csr_projects WHERE theme IN ({fam}) AND subarea IS NOT NULL{w}
        GROUP BY subarea, fy ORDER BY subarea, fy""", args).fetchall()
    by: dict[str, dict] = {}
    for r in rows:
        d = by.setdefault(r["subarea"], {"subarea": r["subarea"], "label": SUBAREA_LABELS.get("sub." + r["subarea"]),
                                         "by_fy": [], "recent_cr": 0.0, "recent_funders": set(), "recent_n": 0})
        d["by_fy"].append({"fy": r["fy"], "cr": r["cr"], "n": r["n"], "funders": r["funders"]})
        if r["fy"] >= "2021-22":
            d["recent_cr"] += r["cr"]; d["recent_n"] += r["n"]
    # distinct funders in recent window
    for sub, d in by.items():
        fun = con.execute(f"""SELECT DISTINCT cin FROM csr_projects WHERE theme IN ({fam}) AND subarea=? AND fy>='2021-22'{w}""",
                          (sub, *args)).fetchall()
        d["recent_funders"] = len(fun)
        top = con.execute(f"""SELECT f.name, f.cin, ROUND(SUM(p.spent_cr),2) cr FROM csr_projects p JOIN funders f USING(cin)
                              WHERE p.theme IN ({fam}) AND p.subarea=? AND p.fy>='2021-22'{w}
                              GROUP BY f.cin ORDER BY cr DESC LIMIT 5""", (sub, *args)).fetchall()
        d["top_funders"] = [dict(t) for t in top]
        examples = con.execute(f"""SELECT project_name, fy, state_code, spent_cr, source_row, subarea_rule FROM csr_projects
                                   WHERE theme IN ({fam}) AND subarea=? AND fy>='2021-22'{w} ORDER BY spent_cr DESC LIMIT 5""",
                               (sub, *args)).fetchall()
        d["examples"] = [dict(e) for e in examples]
        d["recent_cr"] = round(d["recent_cr"], 2)
        d["evidence"] = ev.make(con, MCA_CSR.source_id,
                                f"csr_projects where theme in livelihood family, subarea={sub}, fy>=2021-22" + (f", state_code={state_code}" if state_code else ""),
                                f"₹{d['recent_cr']} cr across {d['recent_funders']} funders",
                                [e["source_row"] for e in examples]).as_dict()
    out = sorted(by.values(), key=lambda d: -d["recent_cr"])
    unclassified = con.execute(f"""SELECT ROUND(SUM(spent_cr),2) cr, COUNT(*) n FROM csr_projects
                                   WHERE theme IN ({fam}) AND subarea IS NULL AND fy>='2021-22'{w}""", args).fetchone()
    return {"state_code": state_code, "subareas": out,
            "unclassified": {"cr": unclassified["cr"], "n": unclassified["n"],
                             "note": "Project names too vague for a keyword rule; counted in theme totals but not in any sub-area."},
            "method": "Sub-areas are assigned by keyword rules on the project name as filed (rule id stored per row). "
                      "They measure what funders have reported spending on, not what they will fund next."}
