"""First-pass proposal drafting with enforced citations.

Design:
- The model only ever sees an *evidence pack*: numbered facts, each with a source id and retrieval
  date, plus the CSO's own (consented) statements and the RFP text.
- It must return structured JSON: sections -> paragraphs, each paragraph tagged either
  `evidence` (with the fact ids it rests on) or `cso_to_fill` (a prompt for the CSO to answer).
- Post-check: a paragraph tagged `evidence` whose fact ids are missing or unknown is DROPPED and
  listed under "dropped", never silently kept. That is the whole point.
- If no model credentials are available, `template_draft` produces the same structure from the
  evidence alone, with the narrative left as design-thinking prompts for the CSO.

Model: claude-opus-5 by default (FFRH_DRAFT_MODEL). Credentials come from the Anthropic SDK's
normal chain (ANTHROPIC_API_KEY or an `ant auth login` profile); nothing is stored here.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from ..config import DRAFT_MODEL
from ..ingest.themes import THEME_LABELS, SUBAREA_LABELS
from ..query import funders as fq, matching, evidence as ev

# ------------------------------------------------------------------ evidence pack

def build_evidence_pack(con: sqlite3.Connection, cso_id: str, funder_cin: str | None, rfp_id: int | None) -> dict:
    c = con.execute("SELECT * FROM cso_profiles WHERE cso_id=?", (cso_id,)).fetchone()
    if not c:
        raise KeyError(cso_id)
    fields = json.loads(c["fields_json"] or "{}")
    facts: list[dict] = []

    def add(text: str, e: dict, kind: str) -> str:
        fid = f"F{len(facts) + 1}"
        facts.append({"id": fid, "kind": kind, "text": text, "source_id": e["source_id"], "source_name": e["source_name"],
                      "url": e.get("url"), "retrieved_at": e["retrieved_at"], "locator": e.get("locator", "")})
        return fid

    # CSO facts: only fields whose visibility is 'public' or consent_basis reviewed
    cso_facts = []
    for f, meta in fields.items():
        if meta.get("visibility") == "public" and meta.get("value") not in (None, "", []):
            v = meta["value"]
            if f == "grant_history":
                for g in v[:6]:
                    cso_facts.append(add(
                        f"Grant record: {g.get('funding_agency') or g.get('source_of_funds') or 'unnamed agency'} - "
                        f"{g.get('field_of_work')} ({g.get('from_date')} to {g.get('to_date')}, ₹{g.get('amount_inr') or 0:,.0f})",
                        {"source_id": meta["source_id"], "source_name": "NGO Darpan", "retrieved_at": meta["retrieved_at"],
                         "url": "https://ngodarpan.gov.in/", "locator": f"ngo_grants source_row {g.get('source_row')}"}, "cso"))
            else:
                cso_facts.append(add(f"{f.replace('_', ' ').capitalize()}: {v}",
                                     {"source_id": meta["source_id"], "source_name": "NGO Darpan", "retrieved_at": meta["retrieved_at"],
                                      "url": "https://ngodarpan.gov.in/", "locator": "ngos"}, "cso"))
    if c["programme_summary"]:
        cso_facts.append(add(f"Programme summary (CSO's own statement): {c['programme_summary']}",
                             {"source_id": "ffrh_stand_in_cohort", "source_name": "CSO self-statement", "retrieved_at": c["created_at"],
                              "url": "", "locator": "cso_profiles.programme_summary"}, "cso"))
    withheld = [f for f, m in fields.items() if m.get("visibility") == "consent_required"]

    funder_facts = []
    if funder_cin:
        p = fq.profile(con, funder_cin)
        if p:
            for a in p["attributes"]:
                funder_facts.append(add(f"{p['name']}: {a['text']}", a["evidence"][0], "funder"))
    rfp_facts, rfp_text, rfp = [], "", None
    if rfp_id:
        rfp = con.execute("SELECT * FROM rfps WHERE rfp_id=?", (rfp_id,)).fetchone()
        if rfp:
            e = ev.make(con, rfp["source_id"], "rfps.body_text", url=rfp["url"], retrieved_at=rfp["retrieved_at"]).as_dict()
            rfp_facts.append(add(f"RFP '{rfp['title']}' issued by {rfp['issuer']}; deadline {rfp['deadline'] or 'not stated'}; page retrieved {rfp['retrieved_at']}", e, "rfp"))
            rfp_text = (rfp["body_text"] or "")[:12000]
    return {"cso": {"cso_id": c["cso_id"], "display_name": c["display_name"], "state_code": c["state_code"],
                    "themes": [THEME_LABELS.get(t, t) for t in json.loads(c["themes"])],
                    "subareas": [SUBAREA_LABELS.get("sub." + s, s) for s in json.loads(c["subareas"] or "[]")],
                    "is_stand_in": bool(c["is_stand_in"]), "withheld_fields": withheld},
            "facts": facts, "cso_fact_ids": cso_facts, "funder_fact_ids": funder_facts, "rfp_fact_ids": rfp_facts,
            "rfp": dict(rfp) if rfp else None, "rfp_text": rfp_text}


# ------------------------------------------------------------------ output schema

class Paragraph(BaseModel):
    kind: Literal["evidence", "cso_to_fill"]
    text: str = Field(description="For 'evidence': a claim that rests ONLY on the listed fact ids. For 'cso_to_fill': a concrete question the CSO must answer, with a one-line hint on what a strong answer contains.")
    fact_ids: list[str] = Field(default_factory=list, description="Ids like F3 from the evidence pack. Required and non-empty for 'evidence' paragraphs; empty for 'cso_to_fill'.")


class Section(BaseModel):
    title: str
    paragraphs: list[Paragraph]


class Draft(BaseModel):
    sections: list[Section]
    notes_to_cso: list[str] = Field(default_factory=list, description="Short notes on what the draft could not say and why.")


SECTION_PLAN = [
    "Summary", "The problem in our context", "Why this funder / this call", "What we will do",
    "Evidence we already have", "Budget and ask", "Risks and what we do not yet know",
]

SYSTEM = """You draft first-pass funding proposals for civil society organisations in North East India.
You are given an EVIDENCE PACK of numbered facts. Rules, in order of importance:
1. Every 'evidence' paragraph must rest only on facts in the pack and list their ids. Do not add numbers, names,
   priorities, quotes or claims that are not in the pack. If you are tempted to write something unsupported,
   write a 'cso_to_fill' paragraph instead: a sharp question the organisation must answer in its own words.
2. Do not describe a funder's intentions, priorities or preferences. You may only describe what it has filed or published (the facts).
3. Prefer specific over generic. A 'cso_to_fill' question should push the organisation toward design thinking:
   who exactly, what changed, how they know, what they would stop doing.
4. Plain English, short paragraphs, no marketing language. Indian rupees as ₹ lakh / ₹ crore.
5. Cover these sections in this order: """ + "; ".join(SECTION_PLAN) + "."


def _facts_block(pack: dict) -> str:
    lines = [f"[{f['id']}] ({f['kind']}) {f['text']}  — source: {f['source_name']}, retrieved {f['retrieved_at']}" for f in pack["facts"]]
    return "\n".join(lines)


def _check(draft: Draft, pack: dict) -> tuple[list[dict], list[dict]]:
    known = {f["id"] for f in pack["facts"]}
    kept, dropped = [], []
    for s in draft.sections:
        sec = {"title": s.title, "paragraphs": []}
        for p in s.paragraphs:
            if p.kind == "evidence":
                ids = [i for i in p.fact_ids if i in known]
                if not ids or len(ids) != len(p.fact_ids):
                    dropped.append({"section": s.title, "text": p.text, "fact_ids": p.fact_ids,
                                    "why": "no valid fact id" if not ids else f"unknown fact ids: {sorted(set(p.fact_ids) - known)}"})
                    continue
                sec["paragraphs"].append({"kind": "evidence", "text": p.text, "fact_ids": ids})
            else:
                sec["paragraphs"].append({"kind": "cso_to_fill", "text": p.text, "fact_ids": []})
        kept.append(sec)
    return kept, dropped


# ------------------------------------------------------------------ two drafting paths

def template_draft(pack: dict) -> Draft:
    """No model: lay out the structure from evidence, and ask the CSO the design questions."""
    F = {f["id"]: f for f in pack["facts"]}
    cso, fun, rfp = pack["cso_fact_ids"], pack["funder_fact_ids"], pack["rfp_fact_ids"]
    name = pack["cso"]["display_name"]
    secs = []
    secs.append(Section(title="Summary", paragraphs=[
        Paragraph(kind="evidence", text=f"{name} is a registered organisation working on {', '.join(pack['cso']['themes'])} in {pack['cso']['state_code']}.", fact_ids=cso[:1]) if cso else
        Paragraph(kind="cso_to_fill", text="In two sentences: who you are, where you work, and the one programme this proposal is about."),
        Paragraph(kind="cso_to_fill", text="What is the single result you want this grant to produce, for whom, by when? (Strong answer: a number, a place, a date.)"),
    ]))
    secs.append(Section(title="The problem in our context", paragraphs=[
        Paragraph(kind="cso_to_fill", text="Describe the problem as the people you work with describe it, not as a sector report does. What did you hear in the last three months that changed your view?"),
        Paragraph(kind="cso_to_fill", text="What is already being tried locally (by government, other NGOs, the community) and why is it not enough?"),
    ]))
    why = [Paragraph(kind="evidence", text=F[i]["text"].split(": ", 1)[-1], fact_ids=[i]) for i in fun[:4]]
    why += [Paragraph(kind="evidence", text=F[i]["text"], fact_ids=[i]) for i in rfp[:1]]
    why.append(Paragraph(kind="cso_to_fill", text="Why does your work fit what this funder has actually filed or published above? Point to the specific line, not to a general impression."))
    secs.append(Section(title="Why this funder / this call", paragraphs=why))
    secs.append(Section(title="What we will do", paragraphs=[
        Paragraph(kind="cso_to_fill", text="List the three to five activities, each with who does it, for whom, how often. Cut anything you cannot explain in one sentence."),
        Paragraph(kind="cso_to_fill", text="What will you deliberately NOT do, and why?"),
    ]))
    ev_par = [Paragraph(kind="evidence", text=F[i]["text"], fact_ids=[i]) for i in cso[1:7]]
    ev_par.append(Paragraph(kind="cso_to_fill", text="What evidence do you hold from your own programme (baseline, follow-up, case records)? Name the document and the year."))
    secs.append(Section(title="Evidence we already have", paragraphs=ev_par))
    secs.append(Section(title="Budget and ask", paragraphs=[
        Paragraph(kind="cso_to_fill", text="Total ask in ₹ lakh, split into people, programme costs, and overheads. State the share of your annual budget this would represent."),
    ]))
    secs.append(Section(title="Risks and what we do not yet know", paragraphs=[
        Paragraph(kind="cso_to_fill", text="Name two things that could go wrong and what you would do about each. Name one thing you genuinely do not know yet."),
    ]))
    notes = ["Generated without a language model: structure and evidence only; narrative left as questions for the organisation."]
    if pack["cso"]["withheld_fields"]:
        notes.append("Fields withheld pending consent review: " + ", ".join(pack["cso"]["withheld_fields"]) + ".")
    return Draft(sections=secs, notes_to_cso=notes)


def model_draft(pack: dict, model: str = DRAFT_MODEL) -> tuple[Draft, str]:
    import anthropic  # imported here so the app runs without the SDK configured
    client = anthropic.Anthropic()
    user = ("EVIDENCE PACK\n" + _facts_block(pack) +
            (f"\n\nRFP TEXT (public page, retrieved {pack['rfp']['retrieved_at']}):\n{pack['rfp_text']}" if pack.get("rfp_text") else "") +
            f"\n\nORGANISATION: {pack['cso']['display_name']} ({pack['cso']['state_code']}); themes: {', '.join(pack['cso']['themes'])}."
            f"\nFields withheld pending consent review (do not guess them): {', '.join(pack['cso']['withheld_fields']) or 'none'}."
            "\n\nWrite the first-pass draft as structured output.")
    with client.messages.stream(model=model, max_tokens=16000, system=SYSTEM,
                                messages=[{"role": "user", "content": user}],
                                output_config={"format": {"type": "json_schema", "schema": Draft.model_json_schema()}}) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("model declined the request")
    text = next(b.text for b in msg.content if b.type == "text")
    return Draft.model_validate_json(text), msg.model


def draft(con: sqlite3.Connection, cso_id: str, funder_cin: str | None = None, rfp_id: int | None = None,
          use_model: bool = True) -> dict:
    pack = build_evidence_pack(con, cso_id, funder_cin, rfp_id)
    mode, model_used, error = "template", None, None
    if use_model:
        try:
            d, model_used = model_draft(pack)
            mode = "model"
        except Exception as e:  # noqa: BLE001 - any failure falls back to the template path, and says so
            error = f"{type(e).__name__}: {str(e)[:200]}"
            d = template_draft(pack)
    else:
        d = template_draft(pack)
    kept, dropped = _check(d, pack)
    out = {"cso_id": cso_id, "funder_cin": funder_cin, "rfp_id": rfp_id, "mode": mode, "model": model_used,
           "model_error": error, "sections": kept, "dropped": dropped, "notes_to_cso": d.notes_to_cso,
           "facts": pack["facts"], "withheld_fields": pack["cso"]["withheld_fields"],
           "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    cur = con.execute("INSERT INTO drafts(cso_id,rfp_id,funder_cin,mode,model,created_at,draft_json,dropped_json) VALUES(?,?,?,?,?,?,?,?)",
                      (cso_id, rfp_id, funder_cin, mode, model_used, out["created_at"], json.dumps(out), json.dumps(dropped)))
    con.commit()
    out["draft_id"] = cur.lastrowid
    return out
