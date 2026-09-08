"""Narrative and funding-signal feed for the advisory view. 80/20 weighting is applied at display time."""
from __future__ import annotations

import json
import sqlite3


def feed(con: sqlite3.Connection, limit: int = 60, state_code: str | None = None) -> dict:
    rows = con.execute("SELECT n.*, s.name AS source_name, s.publisher FROM narrative_items n JOIN sources s USING(source_id) ORDER BY published_at DESC, item_id DESC LIMIT 400").fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["funder_cins"] = json.loads(d["funder_cins"] or "[]"); d["states"] = json.loads(d["states"] or "[]"); d["themes"] = json.loads(d["themes"] or "[]")
        if state_code and state_code not in d["states"]:
            continue
        d["funders"] = [con.execute("SELECT name FROM funders WHERE cin=?", (c,)).fetchone()[0] for c in d["funder_cins"]]
        items.append(d)
    funding = [i for i in items if i["signal_type"] == "funding"]
    narrative = [i for i in items if i["signal_type"] == "narrative"]
    n_f = max(1, int(limit * 0.8)); n_n = max(1, limit - n_f)
    return {"funding": funding[:n_f], "narrative": narrative[:n_n],
            "counts": {"funding": len(funding), "narrative": len(narrative)},
            "weighting": "Display budget is 80% funding signals, 20% broader narrative, per the advisory group's request.",
            "method": "Public RSS feeds only (headline, link, date, short summary). Funder names matched by rule against the CSR filer list. "
                      "No LinkedIn scraping; executive posts can be logged manually with a URL."}


def funder_priority_shifts(con: sqlite3.Connection, min_cr: float = 1.0, limit: int = 20) -> list[dict]:
    """Funders whose NE theme mix moved between FY2021-22 and FY2023-24 - a filed, not inferred, signal."""
    rows = con.execute("""
        SELECT f.cin, f.name, p.theme, p.fy, SUM(p.spent_cr) cr FROM csr_projects p JOIN funders f USING(cin)
        WHERE p.fy IN ('2021-22','2023-24') GROUP BY f.cin, p.theme, p.fy""").fetchall()
    by: dict[str, dict] = {}
    for r in rows:
        d = by.setdefault(r["cin"], {"cin": r["cin"], "name": r["name"], "2021-22": {}, "2023-24": {}})
        d[r["fy"]][r["theme"]] = r["cr"]
    out = []
    for d in by.values():
        a, b = d["2021-22"], d["2023-24"]
        ta, tb = sum(a.values()), sum(b.values())
        if tb < min_cr:
            continue
        shifts = []
        for t in set(a) | set(b):
            sa = a.get(t, 0) / ta if ta else 0; sb = b.get(t, 0) / tb if tb else 0
            if abs(sb - sa) >= 0.25:
                shifts.append({"theme": t, "share_2021_22": round(sa, 2), "share_2023_24": round(sb, 2)})
        if shifts:
            out.append({"cin": d["cin"], "name": d["name"], "ne_cr_2023_24": round(tb, 2), "shifts": sorted(shifts, key=lambda s: -(s["share_2023_24"] - s["share_2021_22"]))})
    out.sort(key=lambda x: -x["ne_cr_2023_24"])
    return out[:limit]
