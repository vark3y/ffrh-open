"""FastAPI app: open JSON API (/api/v1, documented at /docs) + persona surfaces on the protected layer (/hub)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .config import HUB_TOKEN, NE_STATES, DRAFT_MODEL
from .db import connect, init_schema
from .ingest import news as news_ingest, rfps as rfp_ingest
from .ingest.themes import THEME_LABELS, SUBAREA_LABELS, LIVELIHOOD_FAMILY
from .protected import drafting
from .query import funders as fq, matching, narrative, rfp_match, subareas

WEB = Path(__file__).parent / "web"
app = FastAPI(title="FFRH open data + query API", version="0.1.0",
              description="Open layer: North East India CSR funders, NGO register, sub-area patterns, rule-based matching, "
                          "public signals and curated RFPs. Every attribute carries its source and retrieval date.")
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
templates = Jinja2Templates(directory=WEB / "templates")
STATE_NAMES = matching.STATE_NAMES
PERSONAS = {"team": "FFRH team", "advisory": "Advisory group", "cso": "CSO"}
PERSONA_HOME = {"team": "/hub/team", "advisory": "/hub/advisory", "cso": "/hub/cso"}


def db():
    con = connect(); init_schema(con)
    try:
        yield con
    finally:
        con.close()


def _freshness(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT source_id, name, retrieved_at, personal_data FROM sources ORDER BY retrieved_at DESC")]


def render(request: Request, name: str, con, **ctx):
    persona = request.cookies.get("ffrh_persona")
    return templates.TemplateResponse(request, name, {"request": request, "persona": persona, "personas": PERSONAS,
                                                      "freshness": _freshness(con), "states": STATE_NAMES,
                                                      "theme_labels": THEME_LABELS, "sub_labels": SUBAREA_LABELS, **ctx})


# ------------------------------------------------------------------ open pages
@app.get("/", response_class=HTMLResponse)
def home(request: Request, con=Depends(db)):
    nat = fq.landscape(con)["national"]
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("funders", "csr_projects", "ngos", "narrative_items", "rfps")}
    return render(request, "index.html", con, national=nat[-3:], counts=counts)


@app.get("/funders", response_class=HTMLResponse)
def funders_page(request: Request, q: str | None = None, state: str | None = None, theme: str | None = None, con=Depends(db)):
    rows = fq.list_funders(con, q=q, state_code=state, theme=theme, limit=100)
    return render(request, "funders.html", con, rows=rows, q=q or "", state=state or "", theme=theme or "")


@app.get("/funders/{cin}", response_class=HTMLResponse)
def funder_page(request: Request, cin: str, con=Depends(db)):
    p = fq.profile(con, cin)
    if not p:
        raise HTTPException(404)
    sig = [dict(r) for r in con.execute("SELECT title,url,published_at,retrieved_at,signal_type FROM narrative_items WHERE funder_cins LIKE ? ORDER BY published_at DESC LIMIT 10", (f'%"{cin}"%',))]
    return render(request, "funder.html", con, p=p, signals=sig)


@app.get("/patterns", response_class=HTMLResponse)
def patterns_page(request: Request, state: str | None = None, con=Depends(db)):
    return render(request, "patterns.html", con, data=subareas.attractiveness(con, state or None), state=state or "",
                  landscape=fq.landscape(con))


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, con=Depends(db)):
    rows = [dict(r) for r in con.execute("SELECT * FROM sources ORDER BY retrieved_at DESC")]
    return render(request, "sources.html", con, rows=rows)


@app.get("/dpdp", response_class=HTMLResponse)
def dpdp_page(request: Request, con=Depends(db)):
    notes = (Path(__file__).parent.parent / "DPDP_NOTES.md").read_text() if (Path(__file__).parent.parent / "DPDP_NOTES.md").exists() else "DPDP_NOTES.md missing"
    return render(request, "dpdp.html", con, notes=notes)


# ------------------------------------------------------------------ open JSON API
class MatchBody(BaseModel):
    themes: list[str] = Field(default=["livelihoods"], description="Theme ids, e.g. livelihoods, women, education")
    state_code: str = Field(description="AR, AS, MN, ML, MZ, NL, SK or TR")
    subareas: list[str] = Field(default_factory=list, description="e.g. handloom_craft, skilling, agri_horti")
    districts: list[str] = Field(default_factory=list)
    ask_min_lakh: float | None = None
    ask_max_lakh: float | None = None
    limit: int = 15


@app.get("/api/v1/sources")
def api_sources(con=Depends(db)):
    return [dict(r) for r in con.execute("SELECT * FROM sources")]


@app.get("/api/v1/themes")
def api_themes():
    return {"themes": THEME_LABELS, "livelihood_subareas": {k.split('.', 1)[1]: v for k, v in SUBAREA_LABELS.items()},
            "livelihood_family": sorted(LIVELIHOOD_FAMILY), "states": STATE_NAMES}


@app.get("/api/v1/funders")
def api_funders(q: str | None = None, state: str | None = None, theme: str | None = None, limit: int = 50, offset: int = 0, con=Depends(db)):
    return fq.list_funders(con, q=q, state_code=state, theme=theme, limit=min(limit, 200), offset=offset)


@app.get("/api/v1/funders/{cin}")
def api_funder(cin: str, con=Depends(db)):
    p = fq.profile(con, cin)
    if not p:
        raise HTTPException(404)
    return p


@app.get("/api/v1/landscape")
def api_landscape(con=Depends(db)):
    return fq.landscape(con)


@app.get("/api/v1/subareas")
def api_subareas(state: str | None = None, con=Depends(db)):
    return subareas.attractiveness(con, state)


@app.post("/api/v1/match")
def api_match(body: MatchBody, con=Depends(db)):
    if body.state_code not in STATE_NAMES:
        raise HTTPException(400, "state_code must be one of " + ", ".join(STATE_NAMES))
    return matching.match(con, matching.MatchInput(themes=body.themes, state_code=body.state_code, subareas=body.subareas,
                                                   districts=body.districts, ask_min_lakh=body.ask_min_lakh, ask_max_lakh=body.ask_max_lakh), body.limit)


@app.get("/api/v1/signals")
def api_signals(state: str | None = None, limit: int = 60, con=Depends(db)):
    return narrative.feed(con, limit=limit, state_code=state)


@app.get("/api/v1/signals/priority-shifts")
def api_shifts(con=Depends(db)):
    return narrative.funder_priority_shifts(con)


@app.get("/api/v1/rfps")
def api_rfps(con=Depends(db)):
    return [dict(r, body_text=None) for r in con.execute("SELECT * FROM rfps ORDER BY deadline IS NULL, deadline")]


@app.get("/api/v1/ngos")
def api_ngos(q: str | None = None, state: str | None = None, limit: int = 50, con=Depends(db)):
    w, a = ["1=1"], []
    if q: w.append("name LIKE ?"); a.append(f"%{q}%")
    if state: w.append("state_code=?"); a.append(state)
    rows = con.execute(f"""SELECT n.darpan_id, n.name, n.state_code, n.city, COUNT(g.grant_id) grant_rows,
                           GROUP_CONCAT(DISTINCT g.theme) themes, n.source_id FROM ngos n LEFT JOIN ngo_grants g USING(darpan_id)
                           WHERE {' AND '.join(w)} GROUP BY n.darpan_id ORDER BY grant_rows DESC LIMIT ?""", (*a, min(limit, 200))).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ protected layer (demo gate)
def _log(con, request: Request, cso_id: str | None = None):
    con.execute("INSERT INTO access_log(at,persona,path,cso_id) VALUES(?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), request.cookies.get("ffrh_persona", "?"), request.url.path, cso_id))
    con.commit()


def require_persona(request: Request):
    p = request.cookies.get("ffrh_persona")
    if request.cookies.get("ffrh_token") != HUB_TOKEN or p not in PERSONAS:
        raise HTTPException(303, headers={"Location": "/hub/enter"})
    return p


def surface(needed: str):
    """Guard a persona's landing surface so the badge always matches the screen.

    Landing on another persona's surface (by typing the URL or clicking the sidebar) switches you to
    that persona rather than showing their screen under your name. Deeper pages — a CSO's flow, a
    draft — stay open to any signed-in persona, because the team board deliberately links into them.
    """
    def dep(request: Request, persona=Depends(require_persona)):
        if persona != needed:
            raise HTTPException(303, headers={"Location": f"/hub/as/{needed}"})
        return persona
    return dep


@app.get("/hub/enter", response_class=HTMLResponse)
def hub_enter(request: Request, con=Depends(db)):
    return render(request, "hub_enter.html", con)


@app.post("/hub/enter")
def hub_enter_post(persona: str = Form(...), token: str = Form(...)):
    if token != HUB_TOKEN or persona not in PERSONAS:
        return RedirectResponse("/hub/enter?bad=1", status_code=303)
    resp = RedirectResponse(PERSONA_HOME[persona], status_code=303)
    resp.set_cookie("ffrh_persona", persona, httponly=True, samesite="lax")
    resp.set_cookie("ffrh_token", token, httponly=True, samesite="lax")
    return resp


@app.get("/hub/as/{persona}")
def hub_switch(request: Request, persona: str):
    """Switch which persona you are viewing as, in one click.

    All three surfaces stay reachable during a demo. Switching rewrites the persona cookie so the
    badge and the access log say who was actually looking, rather than letting one persona browse
    another's screen under the wrong name.
    """
    if request.cookies.get("ffrh_token") != HUB_TOKEN or persona not in PERSONAS:
        return RedirectResponse("/hub/enter", status_code=303)
    resp = RedirectResponse(PERSONA_HOME[persona], status_code=303)
    resp.set_cookie("ffrh_persona", persona, httponly=True, samesite="lax")
    return resp


@app.get("/hub/leave")
def hub_leave():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("ffrh_persona"); resp.delete_cookie("ffrh_token")
    return resp


@app.get("/hub", response_class=HTMLResponse)
def hub_home(request: Request, persona=Depends(require_persona)):
    return RedirectResponse(PERSONA_HOME[persona], status_code=303)


def _cohort(con):
    rows = []
    for c in con.execute("SELECT * FROM cso_profiles ORDER BY cso_id"):
        d = dict(c); d["themes"] = json.loads(d["themes"]); d["subareas"] = json.loads(d["subareas"] or "[]")
        d["districts"] = json.loads(d["districts"] or "[]"); d["fields"] = json.loads(d["fields_json"] or "{}")
        rows.append(d)
    return rows


@app.get("/hub/team", response_class=HTMLResponse)
def hub_team(request: Request, persona=Depends(surface("team")), con=Depends(db)):
    _log(con, request)
    cohort = _cohort(con)
    board = []
    for c in cohort:
        m = matching.match_for_cso(con, c["cso_id"], limit=5)
        r = rfp_match.match_rfps(con, c["cso_id"])
        board.append({"cso": c, "top": m["matches"], "rfps": [x for x in r["rfps"] if x["score"] >= 50][:3]})
    return render(request, "hub_team.html", con, board=board)


@app.get("/hub/advisory", response_class=HTMLResponse)
def hub_advisory(request: Request, state: str | None = None, persona=Depends(surface("advisory")), con=Depends(db)):
    _log(con, request)
    return render(request, "hub_advisory.html", con, landscape=fq.landscape(con), shifts=narrative.funder_priority_shifts(con),
                  feed=narrative.feed(con, limit=40, state_code=state or None), state=state or "",
                  cohort=_cohort(con), patterns=subareas.attractiveness(con))


@app.get("/hub/cso", response_class=HTMLResponse)
def hub_cso_pick(request: Request, persona=Depends(surface("cso")), con=Depends(db)):
    return render(request, "hub_cso_pick.html", con, cohort=_cohort(con))


@app.get("/hub/cso/{cso_id}", response_class=HTMLResponse)
def hub_cso(request: Request, cso_id: str, step: int = 1, persona=Depends(require_persona), con=Depends(db)):
    _log(con, request, cso_id)
    c = next((x for x in _cohort(con) if x["cso_id"] == cso_id), None)
    if not c:
        raise HTTPException(404)
    ctx = {"c": c, "step": step}
    if step >= 2:
        ctx["patterns"] = subareas.attractiveness(con, c["state_code"])
        ctx["patterns_all"] = subareas.attractiveness(con)
    if step >= 3:
        ctx["matches"] = matching.match_for_cso(con, cso_id, limit=10)
    if step >= 4:
        ctx["rfps"] = rfp_match.match_rfps(con, cso_id)
    if step >= 5:
        ctx["drafts"] = [dict(r) for r in con.execute("SELECT draft_id, created_at, mode, model, funder_cin, rfp_id FROM drafts WHERE cso_id=? ORDER BY draft_id DESC", (cso_id,))]
        ctx["model_name"] = DRAFT_MODEL
    return render(request, "hub_cso.html", con, **ctx)


@app.post("/hub/cso/{cso_id}/profile")
def hub_cso_profile(request: Request, cso_id: str, themes: list[str] = Form(default=[]), subareas_: list[str] = Form(default=[], alias="subareas"),
                    districts: str = Form(""), programme_summary: str = Form(""), ask_min_lakh: str = Form(""), ask_max_lakh: str = Form(""),
                    persona=Depends(require_persona), con=Depends(db)):
    def num(x):
        try: return float(x) if x.strip() else None
        except ValueError: return None
    con.execute("""UPDATE cso_profiles SET themes=?, subareas=?, districts=?, programme_summary=?, ask_min_lakh=?, ask_max_lakh=? WHERE cso_id=?""",
                (json.dumps([t for t in themes if t in THEME_LABELS] or ["livelihoods"]), json.dumps(subareas_),
                 json.dumps([d.strip() for d in districts.split(",") if d.strip()]), programme_summary.strip() or None,
                 num(ask_min_lakh), num(ask_max_lakh), cso_id))
    con.commit()
    return RedirectResponse(f"/hub/cso/{cso_id}?step=2", status_code=303)


@app.post("/hub/cso/{cso_id}/draft")
def hub_cso_draft(request: Request, cso_id: str, funder_cin: str = Form(""), rfp_id: str = Form(""), use_model: str = Form(""),
                  persona=Depends(require_persona), con=Depends(db)):
    d = drafting.draft(con, cso_id, funder_cin or None, int(rfp_id) if rfp_id.strip() else None, use_model=bool(use_model))
    return RedirectResponse(f"/hub/draft/{d['draft_id']}", status_code=303)


@app.get("/hub/draft/{draft_id}", response_class=HTMLResponse)
def hub_draft(request: Request, draft_id: int, persona=Depends(require_persona), con=Depends(db)):
    r = con.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = json.loads(r["draft_json"]); d["draft_id"] = draft_id
    facts = {f["id"]: f for f in d["facts"]}
    c = con.execute("SELECT display_name, is_stand_in FROM cso_profiles WHERE cso_id=?", (d["cso_id"],)).fetchone()
    return render(request, "hub_draft.html", con, d=d, facts=facts, cso_name=c["display_name"], is_stand_in=c["is_stand_in"])


@app.post("/hub/signal")
def hub_signal(request: Request, url: str = Form(...), title: str = Form(...), note: str = Form(""), states: str = Form(""),
               funder_cin: str = Form(""), persona=Depends(require_persona), con=Depends(db)):
    news_ingest.log_manual(con, url, title, note, [s.strip().upper() for s in states.split(",") if s.strip()], [], [funder_cin] if funder_cin else [])
    return RedirectResponse(request.headers.get("referer", "/hub/advisory"), status_code=303)


@app.post("/hub/rfp")
def hub_rfp(request: Request, url: str = Form(...), title: str = Form(...), issuer: str = Form(""), deadline: str = Form(""),
            states: str = Form(""), themes: str = Form("livelihoods"), persona=Depends(require_persona), con=Depends(db)):
    rfp_ingest.add(con, url, title, issuer, deadline or None, [s.strip().upper() for s in states.split(",") if s.strip()],
                   [t.strip() for t in themes.split(",") if t.strip()])
    return RedirectResponse(request.headers.get("referer", "/hub/team"), status_code=303)


@app.post("/hub/refresh-signals")
def hub_refresh(request: Request, persona=Depends(require_persona), con=Depends(db)):
    stats = news_ingest.fetch_all(con)
    return JSONResponse(stats)
