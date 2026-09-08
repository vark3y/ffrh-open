"""The Patterns page as a sequence of findings rather than a wall of charts.

Each finding is one claim, one supporting visual, and its own evidence. The claims are computed from
the data every time, never written by hand, so if the underlying filings change the sentence changes
with them. A finding that cannot be supported by the data is simply not emitted.

The `visual` field names what the template should draw beside the claim. The template owns the
drawing; this module owns the numbers and the sentence.
"""
from __future__ import annotations

import sqlite3

from ..ingest.themes import LIVELIHOOD_FAMILY, SUBAREA_LABELS, THEME_LABELS
from ..sources import MCA_CSR
from . import evidence as ev, hexmap
from .funders import landscape

RECENT = ("2021-22", "2022-23", "2023-24")
LATEST = "2023-24"
STATE_NAMES = hexmap.STATE_NAMES


def _cr(x: float) -> str:
    return f"₹{x:,.0f} crore" if abs(x) >= 10 else f"₹{x:,.2f} crore"


def build(con: sqlite3.Connection) -> list[dict]:
    src = MCA_CSR.source_id
    land = landscape(con)
    out: list[dict] = []

    # ---------------------------------------------------------------- 1. the gap
    nat = {r["fy"]: r for r in land["national"]}
    last = nat.get(LATEST)
    if last:
        first_recent = nat.get("2021-22")
        direction = ("roughly flat" if not first_recent or abs(last["ne_share_pct"] - first_recent["ne_share_pct"]) < 0.25
                     else "rising" if last["ne_share_pct"] > first_recent["ne_share_pct"] else "falling")
        out.append({
            "id": "share",
            "kicker": "The size of the gap",
            "title": f"The North East receives {last['ne_share_pct']}% of India's filed CSR spend",
            "say": (f"In FY{LATEST}, companies reported {_cr(last['national_cr'])} of corporate social responsibility "
                    f"spending across India. {_cr(last['ne_cr'])} of it went to the eight North East states. "
                    f"Across the last three filed years the share has been {direction}."),
            "visual": "share_series",
            "data": land["national"],
            "evidence": [ev.make(con, src, "national_totals, all filed years",
                                 f"{last['ne_share_pct']}% of {_cr(last['national_cr'])}").as_dict()],
            "caveat": ("This is the project-level ledger. It excludes contributions companies report without "
                       "allocating to a state, so it is not the same figure as a national CSR total."),
        })

    # ---------------------------------------------------------------- 2. concentration inside the region
    hx = hexmap.build(con, fy=LATEST)
    if hx["lead"]:
        top_two = hx["tiles"][:2]
        bottom_three = hx["tiles"][-3:]
        out.append({
            "id": "where",
            "kicker": "Where it lands",
            "title": f"Inside the region, {hx['lead']['name']} takes {hx['tiles'][0]['share']:.0%} of it",
            "say": (f"{hx['lead']['name']} received {_cr(hx['lead']['cr'])} in FY{LATEST}, about {hx['lead']['ratio']} times "
                    f"the next state. {top_two[0]['name']} and {top_two[1]['name']} together account for "
                    f"{(top_two[0]['share'] + top_two[1]['share']):.0%} of North East CSR spend. The three smallest, "
                    f"{', '.join(t['name'] for t in reversed(bottom_three))}, share "
                    f"{sum(t['share'] for t in bottom_three):.0%} between them."),
            "visual": "hexmap",
            "data": hx,
            "evidence": [ev.make(con, src, f"csr_projects grouped by state_code, fy={LATEST}",
                                 f"{hx['lead']['name']} {_cr(hx['lead']['cr'])}").as_dict()],
            "caveat": "A state's absence here is a gap in filings, not proof that nothing was funded there.",
        })

    # ---------------------------------------------------------------- 3. what themes get funded
    themes = [r for r in land["by_theme_fy"] if r["fy"] == LATEST]
    if themes:
        total = sum(r["cr"] for r in themes)
        liv = [r for r in themes if r["theme"] in LIVELIHOOD_FAMILY]
        liv_cr = sum(r["cr"] for r in liv)
        top = themes[0]
        out.append({
            "id": "themes",
            "kicker": "What it funds",
            "title": f"{THEME_LABELS.get(top['theme'], top['theme'])} takes the largest share, not livelihoods",
            "say": (f"In FY{LATEST}, {THEME_LABELS.get(top['theme'], top['theme']).lower()} accounted for "
                    f"{_cr(top['cr'])}, {top['cr'] / total:.0%} of North East CSR spend, across {top['funders']} funders. "
                    f"The whole livelihoods family, which is where the current cohort works, came to {_cr(liv_cr)}, "
                    f"{liv_cr / total:.0%} of the total."),
            "visual": "theme_bars",
            "data": themes,
            "evidence": [ev.make(con, src, f"csr_projects grouped by theme, fy={LATEST}",
                                 f"{THEME_LABELS.get(top['theme'], top['theme'])} {_cr(top['cr'])}").as_dict()],
            "caveat": "Themes are the Schedule VII categories as filed by the company, not our own classification.",
        })

    # ---------------------------------------------------------------- 4. inside livelihoods
    fam = ",".join(f"'{t}'" for t in LIVELIHOOD_FAMILY)
    subs = con.execute(f"""SELECT subarea, ROUND(SUM(spent_cr),2) cr, COUNT(*) n, COUNT(DISTINCT cin) funders
                           FROM csr_projects WHERE theme IN ({fam}) AND subarea IS NOT NULL AND fy>='2021-22'
                           GROUP BY subarea ORDER BY cr DESC""").fetchall()
    uncl = con.execute(f"""SELECT ROUND(SUM(spent_cr),2) cr, COUNT(*) n FROM csr_projects
                           WHERE theme IN ({fam}) AND subarea IS NULL AND fy>='2021-22'""").fetchone()
    if subs:
        named = [s for s in subs if s["subarea"] != "generic_livelihood"]
        top_named = named[0] if named else subs[0]
        classified = sum(s["cr"] for s in subs)
        out.append({
            "id": "subareas",
            "kicker": "Inside livelihoods",
            "title": f"Of the sub-areas we can name, {SUBAREA_LABELS.get('sub.' + top_named['subarea'], top_named['subarea']).lower()} draws the most",
            "say": (f"Across FY2021-22 to FY{LATEST}, {_cr(top_named['cr'])} went to "
                    f"{SUBAREA_LABELS.get('sub.' + top_named['subarea'], top_named['subarea']).lower()}, from "
                    f"{top_named['funders']} funders. But {_cr(uncl['cr'])} of livelihood-family spending sits in "
                    f"project names too vague for any rule to classify, against {_cr(classified)} we can place. "
                    f"That unclassified pile is larger than every named sub-area combined."),
            "visual": "subarea_bars",
            "data": [dict(s, label=SUBAREA_LABELS.get("sub." + s["subarea"], s["subarea"])) for s in subs],
            "extra": {"unclassified_cr": uncl["cr"], "unclassified_n": uncl["n"], "classified_cr": round(classified, 2)},
            "evidence": [ev.make(con, src, "csr_projects, livelihood family, subarea rules, fy>=2021-22",
                                 f"{_cr(top_named['cr'])} to {top_named['subarea']}").as_dict()],
            "caveat": ("Sub-areas come from keyword rules on the project name as filed. The rule that fired is stored "
                       "on every row, so any classification can be checked or challenged."),
        })

    # ---------------------------------------------------------------- 5. how the money travels
    mode = con.execute("""SELECT impl_mode, ROUND(SUM(spent_cr),2) cr, COUNT(DISTINCT cin) funders FROM csr_projects
                          WHERE fy IN ('2021-22','2022-23','2023-24') GROUP BY impl_mode""").fetchall()
    md = {r["impl_mode"]: r for r in mode}
    a, d = (md.get("agency", {"cr": 0})["cr"], md.get("direct", {"cr": 0})["cr"])
    if a + d > 0:
        out.append({
            "id": "route",
            "kicker": "How it travels",
            "title": f"{a / (a + d):.0%} of it is routed through an implementing partner",
            "say": (f"Of the {_cr(a + d)} whose route is stated, {_cr(a)} passed through implementing agencies rather "
                    f"than being spent by the company itself. That is the door a nonprofit can walk through. "
                    f"The filings never name the agency, so who received it is not public."),
            "visual": "route_split",
            "data": [dict(r) for r in mode],
            "evidence": [ev.make(con, src, "csr_projects grouped by impl_mode, fy 2021-22..2023-24",
                                 f"{a / (a + d):.0%} via agencies").as_dict()],
            "caveat": ("This is the single biggest gap in the open data. Linking a funder to the nonprofit it funded "
                       "would need a source carrying both, such as the CSR-1 registry."),
        })

    # ---------------------------------------------------------------- 6. who moved
    shifts = con.execute("""
        SELECT f.cin, f.name, p.theme, p.fy, SUM(p.spent_cr) cr FROM csr_projects p JOIN funders f USING(cin)
        WHERE p.fy IN ('2021-22','2023-24') GROUP BY f.cin, p.theme, p.fy""").fetchall()
    by: dict[str, dict] = {}
    for r in shifts:
        e = by.setdefault(r["cin"], {"cin": r["cin"], "name": r["name"], "2021-22": {}, "2023-24": {}})
        e[r["fy"]][r["theme"]] = r["cr"]
    movers = []
    for e in by.values():
        first, last_ = e["2021-22"], e["2023-24"]
        t1, t2 = sum(first.values()), sum(last_.values())
        if t2 < 5:
            continue
        for th in set(first) | set(last_):
            s1 = first.get(th, 0) / t1 if t1 else 0
            s2 = last_.get(th, 0) / t2 if t2 else 0
            if s2 - s1 >= 0.4:
                movers.append({"name": e["name"], "cin": e["cin"], "theme": th,
                               "from": round(s1, 2), "to": round(s2, 2), "cr": round(t2, 2)})
    movers.sort(key=lambda m: -m["cr"])
    if movers:
        m = movers[0]
        out.append({
            "id": "moved",
            "kicker": "What changed",
            "title": "Some of the largest funders changed what they back, within two years",
            "say": (f"{m['name'].title()} filed {_cr(m['cr'])} in the North East in FY{LATEST}. "
                    f"{THEME_LABELS.get(m['theme'], m['theme'])} went from {m['from']:.0%} to {m['to']:.0%} of its "
                    f"regional spending between FY2021-22 and FY{LATEST}. "
                    f"{len(movers)} funders moved a theme by 40 points or more over that period."),
            "visual": "shift_slopes",
            "data": movers[:8],
            "evidence": [ev.make(con, src, "csr_projects, theme share by funder, fy 2021-22 vs 2023-24",
                                 f"{m['name']}: {m['theme']} {m['from']:.0%} to {m['to']:.0%}").as_dict()],
            "caveat": ("A shift in filings is not a stated change of policy. It may reflect one large project "
                       "starting or ending, and should be read as a prompt to ask, not as a conclusion."),
        })

    # ---------------------------------------------------------------- 7. so what
    reachable = con.execute("""SELECT COUNT(*) FROM (
        SELECT cin, SUM(spent_cr) s FROM csr_projects WHERE fy IN ('2021-22','2022-23','2023-24')
        GROUP BY cin HAVING s >= 1)""").fetchone()[0]
    via_agency = con.execute("""SELECT COUNT(DISTINCT cin) FROM csr_projects
                                WHERE fy IN ('2021-22','2022-23','2023-24') AND impl_mode='agency'""").fetchone()[0]
    out.append({
        "id": "sowhat",
        "kicker": "What to do with this",
        "title": f"{reachable} funders are worth a conversation, and {via_agency} already work through partners",
        "say": (f"{reachable} companies filed at least ₹1 crore of North East spending in the last three years. "
                f"{via_agency} of all North East filers routed money through implementing agencies at least once. "
                f"That is the realistic target list, and it is small enough to work through by hand."),
        "visual": "cta",
        "data": [],
        "evidence": [ev.make(con, src, "csr_projects grouped by cin, fy 2021-22..2023-24",
                             f"{reachable} funders over ₹1 crore").as_dict()],
        "caveat": ("Filed spending shows what a funder has done, not what it will approve next. Every match this "
                   "tool produces is a reason to start a conversation, never a prediction of a grant."),
    })
    return out
