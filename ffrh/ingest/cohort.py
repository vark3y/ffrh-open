"""Build the STAND-IN demo cohort from the public register.

This exists only because the FFRH cohort profiles have not been shared yet. Every profile is
flagged is_stand_in=1 and carries only public-register fields. When the real profiles arrive,
they are loaded through the same table with consent_basis set per field (see DPDP_NOTES.md).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

from ..sources import STAND_IN_COHORT, NGO_DARPAN

TARGET = 12

FIELD_TEMPLATE = {
    # field: visibility for the demo. 'public' = from a public register; 'consent_required'
    # = would come from FFRH's profile doc and is NOT loaded until the consent basis is reviewed.
    "registered_name": {"visibility": "public", "consent_basis": "public register (NGO Darpan)"},
    "state": {"visibility": "public", "consent_basis": "public register (NGO Darpan)"},
    "city": {"visibility": "public", "consent_basis": "public register (NGO Darpan)"},
    "grant_history": {"visibility": "public", "consent_basis": "public register (NGO Darpan)"},
    "programme_summary": {"visibility": "consent_required", "consent_basis": "NOT REVIEWED - FFRH profile doc"},
    "current_funders": {"visibility": "consent_required", "consent_basis": "NOT REVIEWED - FFRH profile doc"},
    "annual_budget": {"visibility": "consent_required", "consent_basis": "NOT REVIEWED - CSO financials"},
    "future_ready_score": {"visibility": "consent_required", "consent_basis": "NOT REVIEWED - FFRH assessment"},
    "contact_person": {"visibility": "consent_required", "consent_basis": "NOT REVIEWED - personal data (DPDP s.6)"},
}


def build(con: sqlite3.Connection, target: int = TARGET) -> dict:
    con.execute("DELETE FROM cso_profiles WHERE is_stand_in=1")
    # Candidates: NE NGOs with >=2 livelihood-classified grant rows and at least one positive amount.
    cands = con.execute(
        """SELECT n.darpan_id, n.name, n.state_code, n.city,
                  SUM(CASE WHEN g.theme='livelihoods' THEN 1 ELSE 0 END) AS liv_rows,
                  SUM(CASE WHEN g.theme='women' THEN 1 ELSE 0 END) AS women_rows,
                  SUM(COALESCE(g.amount_inr,0)) AS amt, COUNT(*) AS rows_
           FROM ngos n JOIN ngo_grants g ON g.darpan_id=n.darpan_id
           GROUP BY n.darpan_id HAVING liv_rows>=2 AND amt>0
           ORDER BY liv_rows DESC, amt DESC""").fetchall()
    # Spread across states: round-robin by state so the cohort is not all Assam/Manipur.
    by_state: dict[str, list] = {}
    for c in cands:
        by_state.setdefault(c["state_code"], []).append(c)
    chosen = []
    while len(chosen) < target and any(by_state.values()):
        for sc in sorted(by_state):
            if by_state[sc] and len(chosen) < target:
                chosen.append(by_state[sc].pop(0))
    today = date.today().isoformat()
    for k, c in enumerate(chosen, start=1):
        grants = con.execute(
            """SELECT source_of_funds, funding_agency, field_of_work, theme, from_date, to_date, amount_inr, source_row
               FROM ngo_grants WHERE darpan_id=? AND theme IS NOT NULL ORDER BY from_date DESC LIMIT 8""",
            (c["darpan_id"],)).fetchall()
        themes = ["livelihoods"] + (["women"] if c["women_rows"] else [])
        fields = {}
        for f, meta in FIELD_TEMPLATE.items():
            entry = dict(meta)
            if meta["visibility"] == "public":
                entry["source_id"] = NGO_DARPAN.source_id
                entry["retrieved_at"] = "2026-05-17"
                entry["value"] = {"registered_name": c["name"], "state": c["state_code"], "city": c["city"],
                                  "grant_history": [dict(g) for g in grants]}[f]
            else:
                entry["value"] = None
            fields[f] = entry
        con.execute(
            """INSERT INTO cso_profiles(cso_id,darpan_id,display_name,is_stand_in,state_code,districts,themes,subareas,
               programme_summary,ask_min_lakh,ask_max_lakh,fields_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"standin-{k:02d}", c["darpan_id"], c["name"].title(), 1, c["state_code"],
             json.dumps([c["city"]] if c["city"] else []), json.dumps(themes), json.dumps([]),
             None, None, None, json.dumps(fields), today))
    con.commit()
    return {"cohort": len(chosen), "candidates": len(cands)}
