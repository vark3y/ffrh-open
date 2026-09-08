"""CSO -> funder matching. Deterministic, rule-scored, every reason carries evidence.

Input never needs anything personal: themes, sub-areas, a state, optional districts, an ask range.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from ..ingest.themes import THEME_LABELS, SUBAREA_LABELS, LIVELIHOOD_FAMILY
from ..sources import MCA_CSR
from . import evidence as ev

RECENT = ("2021-22", "2022-23", "2023-24")
STATE_NAMES = {"AR": "Arunachal Pradesh", "AS": "Assam", "MN": "Manipur", "ML": "Meghalaya",
               "MZ": "Mizoram", "NL": "Nagaland", "SK": "Sikkim", "TR": "Tripura"}

WEIGHTS = {
    "theme": 25,       # spent on the CSO's theme in the NE recently
    "state": 20,       # spent in the CSO's state recently
    "district": 10,    # spent in one of the CSO's districts
    "subarea": 10,     # spent on the same livelihood sub-area
    "agency": 10,      # routes money through implementing agencies (i.e. funds NGOs at all)
    "recency": 10,     # active in the latest FY
    "scale": 10,       # size of recent NE spend (log scale; ₹10 cr+ earns full points)
    "signal": 5,       # a logged/news funding signal (kept small on purpose)
}


@dataclass
class MatchInput:
    themes: list[str]
    state_code: str
    subareas: list[str] = field(default_factory=list)
    districts: list[str] = field(default_factory=list)
    ask_min_lakh: float | None = None
    ask_max_lakh: float | None = None


def match(con: sqlite3.Connection, inp: MatchInput, limit: int = 15) -> dict:
    src = MCA_CSR.source_id
    themes = [t for t in inp.themes if t in THEME_LABELS] or ["livelihoods"]
    fam = set(themes)
    if fam & LIVELIHOOD_FAMILY:
        fam |= LIVELIHOOD_FAMILY  # rural development / women money is reachable for livelihood CSOs
    theme_sql = ",".join("?" * len(fam))
    # Candidate pool: any funder with NE spend in the recent window.
    cands = con.execute("""SELECT cin, ROUND(SUM(spent_cr),3) total FROM csr_projects
                           WHERE fy IN ('2021-22','2022-23','2023-24') GROUP BY cin HAVING total>0""").fetchall()
    results = []
    for c in cands:
        cin = c["cin"]
        reasons, score = [], 0.0

        def rows(sql, args):
            return con.execute(sql, args).fetchall()

        th = rows(f"""SELECT theme, ROUND(SUM(spent_cr),3) cr, COUNT(*) n, GROUP_CONCAT(source_row) sr FROM csr_projects
                      WHERE cin=? AND fy IN ('2021-22','2022-23','2023-24') AND theme IN ({theme_sql}) GROUP BY theme ORDER BY cr DESC""",
                  (cin, *fam))
        if th:
            exact = [t for t in th if t["theme"] in themes]
            pick = exact or th
            share = min(1.0, sum(t["cr"] for t in pick) / c["total"]) if c["total"] else 0
            pts = WEIGHTS["theme"] * (0.6 + 0.4 * share) * (1.0 if exact else 0.6)
            score += pts
            t = pick[0]
            reasons.append(ev.claim(
                f"Spent ₹{sum(x['cr'] for x in pick):.2f} crore in the North East on {', '.join(THEME_LABELS[x['theme']] for x in pick)} "
                f"in FY22-24 ({sum(x['n'] for x in pick)} project lines, {share:.0%} of its NE spend)"
                + ("" if exact else " - adjacent theme, not an exact match"),
                ev.make(con, src, f"csr_projects where cin={cin}, theme in ({','.join(x['theme'] for x in pick)}), fy 2021-22..2023-24",
                        f"₹{sum(x['cr'] for x in pick):.2f} cr", [int(s) for s in (t["sr"] or "").split(",") if s][:12])))
        st = rows("""SELECT ROUND(SUM(spent_cr),3) cr, COUNT(*) n, GROUP_CONCAT(DISTINCT district) d, GROUP_CONCAT(source_row) sr
                     FROM csr_projects WHERE cin=? AND state_code=? AND fy IN ('2021-22','2022-23','2023-24')""", (cin, inp.state_code))
        if st and st[0]["cr"]:
            s = st[0]
            score += WEIGHTS["state"]
            reasons.append(ev.claim(
                f"Spent ₹{s['cr']:.2f} crore in {STATE_NAMES.get(inp.state_code, inp.state_code)} in FY22-24 "
                f"({s['n']} lines; districts filed: {s['d'] or 'not stated'})",
                ev.make(con, src, f"csr_projects where cin={cin}, state_code={inp.state_code}, fy 2021-22..2023-24",
                        f"₹{s['cr']:.2f} cr", [int(x) for x in (s["sr"] or "").split(",") if x][:12])))
            if inp.districts:
                dq = ",".join("?" * len(inp.districts))
                d = rows(f"""SELECT district, ROUND(SUM(spent_cr),3) cr, GROUP_CONCAT(source_row) sr FROM csr_projects
                             WHERE cin=? AND state_code=? AND fy IN ('2021-22','2022-23','2023-24') AND LOWER(district) IN ({dq})
                             GROUP BY district""", (cin, inp.state_code, *[x.lower() for x in inp.districts]))
                if d:
                    score += WEIGHTS["district"]
                    reasons.append(ev.claim(
                        f"Has filed projects in {', '.join(x['district'] for x in d)} district(s) (₹{sum(x['cr'] for x in d):.2f} crore, FY22-24)",
                        ev.make(con, src, f"csr_projects where cin={cin}, district in ({', '.join(x['district'] for x in d)})",
                                "", [int(y) for x in d for y in (x["sr"] or "").split(",") if y][:12])))
        else:
            # Neighbouring signal: spends in the NE but not this state.
            other = rows("""SELECT GROUP_CONCAT(DISTINCT state_code) s FROM csr_projects WHERE cin=? AND fy IN ('2021-22','2022-23','2023-24')""", (cin,))
            reasons.append(ev.claim(
                f"No filed spend in {STATE_NAMES.get(inp.state_code, inp.state_code)} in FY22-24; NE states filed: {other[0]['s']}",
                ev.make(con, src, f"csr_projects where cin={cin}, fy 2021-22..2023-24", other[0]["s"] or "")))
        if inp.subareas:
            sq = ",".join("?" * len(inp.subareas))
            sb = rows(f"""SELECT subarea, ROUND(SUM(spent_cr),3) cr, COUNT(*) n, GROUP_CONCAT(source_row) sr FROM csr_projects
                          WHERE cin=? AND fy IN ('2021-22','2022-23','2023-24') AND subarea IN ({sq}) GROUP BY subarea ORDER BY cr DESC""",
                      (cin, *inp.subareas))
            if sb:
                score += WEIGHTS["subarea"]
                reasons.append(ev.claim(
                    f"Filed projects in the same sub-area: {', '.join(SUBAREA_LABELS.get('sub.'+x['subarea'], x['subarea']) for x in sb)} "
                    f"(₹{sum(x['cr'] for x in sb):.2f} crore, keyword-classified from project names)",
                    ev.make(con, src, f"csr_projects where cin={cin}, subarea in ({','.join(x['subarea'] for x in sb)})", "",
                            [int(y) for x in sb for y in (x["sr"] or "").split(",") if y][:12])))
        md = rows("""SELECT impl_mode, ROUND(SUM(spent_cr),3) cr FROM csr_projects WHERE cin=? AND fy IN ('2021-22','2022-23','2023-24') GROUP BY impl_mode""", (cin,))
        a = sum(m["cr"] for m in md if m["impl_mode"] == "agency"); d_ = sum(m["cr"] for m in md if m["impl_mode"] == "direct")
        if a + d_ > 0:
            share = a / (a + d_)
            score += WEIGHTS["agency"] * share
            reasons.append(ev.claim(
                f"{share:.0%} of its recent NE spend went through implementing agencies (₹{a:.2f} crore) rather than directly"
                + (" - it works with partners" if share >= 0.5 else " - mostly implements directly; partner route is narrower"),
                ev.make(con, src, f"csr_projects where cin={cin}, impl_mode, fy 2021-22..2023-24", f"{share:.0%}")))
        lat = rows("SELECT ROUND(SUM(spent_cr),3) cr FROM csr_projects WHERE cin=? AND fy='2023-24'", (cin,))
        if lat and lat[0]["cr"]:
            score += WEIGHTS["recency"]
            reasons.append(ev.claim(f"Active in the latest filed year (FY2023-24: ₹{lat[0]['cr']:.2f} crore in the NE)",
                                    ev.make(con, src, f"csr_projects where cin={cin}, fy=2023-24", f"₹{lat[0]['cr']:.2f} cr")))
        sig = rows("""SELECT title, url, published_at, retrieved_at, source_id FROM narrative_items
                      WHERE signal_type='funding' AND funder_cins LIKE ? ORDER BY published_at DESC LIMIT 2""", (f'%"{cin}"%',))
        if sig:
            score += WEIGHTS["signal"]
            for s_ in sig:
                reasons.append(ev.claim(f"Recent funding signal: \"{s_['title']}\"",
                                        ev.make(con, s_["source_id"], "narrative_items", s_["title"], url=s_["url"], retrieved_at=s_["retrieved_at"])))
        import math
        scale = min(1.0, math.log10(1 + c["total"] * 100) / 3)  # ₹10 cr -> ~1.0, ₹1 lakh -> ~0.1
        score += WEIGHTS["scale"] * scale
        reasons.append(ev.claim(f"Recent NE CSR spend of ₹{c['total']:.2f} crore (FY22-24) - scale factor {scale:.2f}",
                                ev.make(con, src, f"csr_projects where cin={cin}, fy 2021-22..2023-24", f"₹{c['total']:.2f} cr")))
        # Scale fit is advisory only (median project size vs ask), reported not scored.
        med = rows("""SELECT spent_cr FROM csr_projects WHERE cin=? AND fy IN ('2021-22','2022-23','2023-24') AND spent_cr>0 ORDER BY spent_cr""", (cin,))
        median_lakh = (med[len(med) // 2]["spent_cr"] * 100) if med else None
        fit = None
        if median_lakh is not None and inp.ask_min_lakh is not None:
            fit = "within its typical project size" if inp.ask_min_lakh <= median_lakh * 3 else "above its typical project size"
        name = con.execute("SELECT name FROM funders WHERE cin=?", (cin,)).fetchone()["name"]
        results.append({"cin": cin, "name": name, "score": round(score, 1), "max_score": sum(WEIGHTS.values()),
                        "ne_recent_cr": c["total"], "median_project_lakh": round(median_lakh, 1) if median_lakh else None,
                        "scale_fit": fit, "reasons": reasons})
    results.sort(key=lambda r: (-r["score"], -r["ne_recent_cr"]))
    return {"input": inp.__dict__, "weights": WEIGHTS, "candidates": len(results), "matches": results[:limit],
            "method": "Rule-based score over filed CSR spend FY2021-22 to FY2023-24. Theme 25, state 20, district 10, "
                      "sub-area 10, agency routing 10, latest-year activity 10, scale 10, logged funding signal 5. "
                      "Scores rank plausibility of a conversation, not likelihood of a grant."}


def match_for_cso(con: sqlite3.Connection, cso_id: str, limit: int = 15) -> dict | None:
    c = con.execute("SELECT * FROM cso_profiles WHERE cso_id=?", (cso_id,)).fetchone()
    if not c:
        return None
    inp = MatchInput(themes=json.loads(c["themes"]), state_code=c["state_code"],
                     subareas=json.loads(c["subareas"] or "[]"), districts=json.loads(c["districts"] or "[]"),
                     ask_min_lakh=c["ask_min_lakh"], ask_max_lakh=c["ask_max_lakh"])
    out = match(con, inp, limit)
    out["cso"] = {"cso_id": c["cso_id"], "display_name": c["display_name"], "is_stand_in": bool(c["is_stand_in"])}
    return out
