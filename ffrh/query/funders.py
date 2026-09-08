"""Funder-level questions over the open data layer. Every attribute returns with evidence."""
from __future__ import annotations

import sqlite3

from ..ingest.themes import THEME_LABELS, SUBAREA_LABELS
from ..sources import MCA_CSR
from . import evidence as ev

LATEST_FY = "2023-24"
RECENT_FYS = ("2021-22", "2022-23", "2023-24")


def _rows_locator(**kw) -> str:
    return "csr_projects where " + ", ".join(f"{k}={v}" for k, v in kw.items() if v is not None)


def list_funders(con: sqlite3.Connection, q: str | None = None, state_code: str | None = None,
                 theme: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    where, args = ["1=1"], []
    if q:
        where.append("f.name LIKE ?"); args.append(f"%{q}%")
    if state_code:
        where.append("p.state_code=?"); args.append(state_code)
    if theme:
        where.append("p.theme=?"); args.append(theme)
    rows = con.execute(f"""
        SELECT f.cin, f.name, f.is_ne_registered,
               ROUND(SUM(p.spent_cr),2) AS ne_spent_cr_all,
               ROUND(SUM(CASE WHEN p.fy IN ('2021-22','2022-23','2023-24') THEN p.spent_cr ELSE 0 END),2) AS ne_spent_cr_recent,
               COUNT(*) AS projects, COUNT(DISTINCT p.state_code) AS states, MAX(p.fy) AS last_fy
        FROM funders f JOIN csr_projects p ON p.cin=f.cin
        WHERE {' AND '.join(where)}
        GROUP BY f.cin ORDER BY ne_spent_cr_recent DESC, ne_spent_cr_all DESC LIMIT ? OFFSET ?""",
        (*args, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def profile(con: sqlite3.Connection, cin: str) -> dict | None:
    f = con.execute("SELECT * FROM funders WHERE cin=?", (cin,)).fetchone()
    if not f:
        return None
    src = MCA_CSR.source_id
    by_fy = con.execute("""SELECT fy, ROUND(SUM(spent_cr),3) cr, COUNT(*) n FROM csr_projects
                           WHERE cin=? GROUP BY fy ORDER BY fy""", (cin,)).fetchall()
    by_state = con.execute("""SELECT state, state_code, ROUND(SUM(spent_cr),3) cr, COUNT(*) n,
                              GROUP_CONCAT(DISTINCT district) districts
                              FROM csr_projects WHERE cin=? AND fy IN ('2021-22','2022-23','2023-24')
                              GROUP BY state_code ORDER BY cr DESC""", (cin,)).fetchall()
    by_theme = con.execute("""SELECT theme, ROUND(SUM(spent_cr),3) cr, COUNT(*) n
                              FROM csr_projects WHERE cin=? AND fy IN ('2021-22','2022-23','2023-24')
                              GROUP BY theme ORDER BY cr DESC""", (cin,)).fetchall()
    by_sub = con.execute("""SELECT subarea, ROUND(SUM(spent_cr),3) cr, COUNT(*) n
                            FROM csr_projects WHERE cin=? AND subarea IS NOT NULL AND fy IN ('2021-22','2022-23','2023-24')
                            GROUP BY subarea ORDER BY cr DESC""", (cin,)).fetchall()
    mode = con.execute("""SELECT impl_mode, ROUND(SUM(spent_cr),3) cr, COUNT(*) n FROM csr_projects
                          WHERE cin=? AND fy IN ('2021-22','2022-23','2023-24') GROUP BY impl_mode""", (cin,)).fetchall()
    projects = con.execute("""SELECT project_id, fy, state_code, district, project_name, sector, theme, subarea,
                              subarea_rule, impl_mode, spent_cr, source_row FROM csr_projects WHERE cin=?
                              ORDER BY fy DESC, spent_cr DESC LIMIT 60""", (cin,)).fetchall()

    def rows_for(**kw) -> list[int]:
        w = " AND ".join(f"{k}=?" for k in kw)
        return [r[0] for r in con.execute(f"SELECT source_row FROM csr_projects WHERE cin=? AND {w} LIMIT 12",
                                          (cin, *kw.values()))]

    attrs = []
    total_recent = sum(r["cr"] for r in by_fy if r["fy"] in RECENT_FYS)
    attrs.append(ev.claim(
        f"Reported ₹{total_recent:.2f} crore of CSR spend in the North East across FY2021-22 to FY2023-24 "
        f"({sum(r['n'] for r in by_fy if r['fy'] in RECENT_FYS)} project lines).",
        ev.make(con, src, _rows_locator(cin=cin, fy="2021-22..2023-24"), f"₹{total_recent:.2f} cr")))
    if by_fy:
        last = by_fy[-1]
        attrs.append(ev.claim(
            f"Most recent North East filing is FY{last['fy']} (₹{last['cr']:.2f} crore, {last['n']} lines).",
            ev.make(con, src, _rows_locator(cin=cin, fy=last["fy"]), f"₹{last['cr']:.2f} cr", rows_for(fy=last["fy"]))))
    for s in by_state[:4]:
        attrs.append(ev.claim(
            f"Spent ₹{s['cr']:.2f} crore in {s['state'].title()} (FY22-24), districts: {s['districts'] or 'not stated'}.",
            ev.make(con, src, _rows_locator(cin=cin, state_code=s["state_code"], fy="2021-22..2023-24"),
                    f"₹{s['cr']:.2f} cr", rows_for(state_code=s["state_code"]))))
    for t in by_theme[:4]:
        attrs.append(ev.claim(
            f"₹{t['cr']:.2f} crore on {THEME_LABELS.get(t['theme'], t['theme'])} in the North East (FY22-24, {t['n']} lines).",
            ev.make(con, src, _rows_locator(cin=cin, theme=t["theme"], fy="2021-22..2023-24"),
                    f"₹{t['cr']:.2f} cr", rows_for(theme=t["theme"]))))
    agency = next((m for m in mode if m["impl_mode"] == "agency"), None)
    direct = next((m for m in mode if m["impl_mode"] == "direct"), None)
    if agency or direct:
        a, d = (agency["cr"] if agency else 0.0), (direct["cr"] if direct else 0.0)
        share = a / (a + d) if (a + d) else 0
        attrs.append(ev.claim(
            f"{share:.0%} of its recent North East spend was routed through implementing agencies "
            f"(₹{a:.2f} crore via agencies vs ₹{d:.2f} crore directly). The filing does not name the agencies.",
            ev.make(con, src, _rows_locator(cin=cin, impl_mode="agency|direct", fy="2021-22..2023-24"), f"{share:.0%}")))
    return {
        "cin": cin, "name": f["name"], "roc": f["roc"], "is_ne_registered": bool(f["is_ne_registered"]),
        "attributes": attrs,
        "by_fy": [dict(r) for r in by_fy], "by_state": [dict(r) for r in by_state],
        "by_theme": [{**dict(r), "label": THEME_LABELS.get(r["theme"], r["theme"])} for r in by_theme],
        "by_subarea": [{**dict(r), "label": SUBAREA_LABELS.get("sub." + r["subarea"], r["subarea"])} for r in by_sub],
        "impl_mode": [dict(r) for r in mode],
        "projects": [dict(r) for r in projects],
        "source": ev.make(con, src, _rows_locator(cin=cin)).as_dict(),
        "caveats": [
            "Amounts are what the company reported to the National CSR Portal; the portal does not name implementing partners.",
            "Absence of a theme or state in the filing is not evidence the funder would refuse it.",
        ],
    }


def landscape(con: sqlite3.Connection) -> dict:
    src = MCA_CSR.source_id
    nat = [dict(r) for r in con.execute("SELECT * FROM national_totals ORDER BY fy")]
    for r in nat:
        r["ne_share_pct"] = round(100 * r["ne_cr"] / r["national_cr"], 2) if r["national_cr"] else None
    by_state_fy = [dict(r) for r in con.execute("""SELECT fy, state_code, ROUND(SUM(spent_cr),2) cr, COUNT(DISTINCT cin) funders
                                                   FROM csr_projects GROUP BY fy, state_code ORDER BY fy, state_code""")]
    by_theme_fy = [dict(r) for r in con.execute("""SELECT fy, theme, ROUND(SUM(spent_cr),2) cr, COUNT(DISTINCT cin) funders
                                                   FROM csr_projects GROUP BY fy, theme ORDER BY fy, cr DESC""")]
    top = list_funders(con, limit=25)
    return {"national": nat, "by_state_fy": by_state_fy, "by_theme_fy": by_theme_fy, "top_funders": top,
            "theme_labels": THEME_LABELS,
            "source": ev.make(con, src, "csr_projects (all NE rows) and national_totals").as_dict()}
