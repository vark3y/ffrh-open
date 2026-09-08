"""The guarantees that matter: nothing shown without a source + date, nothing personal stored, unsourced draft text dropped."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest
from ffrh.db import connect
from ffrh.query import funders, matching, subareas, rfp_match
from ffrh.protected import drafting


@pytest.fixture(scope="module")
def con():
    c = connect(); yield c; c.close()


def _assert_evidence(e: dict):
    assert e["source_id"] and e["source_name"] and e["retrieved_at"], e
    assert len(e["retrieved_at"]) >= 10, "retrieval date must be a full ISO date"


def test_every_funder_attribute_has_evidence(con):
    top = funders.list_funders(con, limit=25)
    for f in top:
        p = funders.profile(con, f["cin"])
        assert p["attributes"], f["name"]
        for a in p["attributes"]:
            assert a["evidence"], a["text"]
            for e in a["evidence"]:
                _assert_evidence(e)


def test_every_match_reason_has_evidence(con):
    for cso in con.execute("SELECT cso_id FROM cso_profiles"):
        m = matching.match_for_cso(con, cso[0], limit=8)
        assert m["matches"]
        for r in m["matches"]:
            assert r["reasons"]
            for reason in r["reasons"]:
                for e in reason["evidence"]:
                    _assert_evidence(e)


def test_subarea_claims_have_evidence(con):
    for d in subareas.attractiveness(con)["subareas"]:
        _assert_evidence(d["evidence"])


def test_rfp_reasons_have_evidence(con):
    r = rfp_match.match_rfps(con, "standin-01")
    for x in r["rfps"]:
        assert x["retrieved_at"]
        for reason in x["reasons"]:
            for e in reason["evidence"]:
                _assert_evidence(e)


def test_no_emails_stored_anywhere(con):
    for t in ("ngos", "ngo_grants", "cso_profiles", "funders", "csr_projects"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        assert not any("email" in c for c in cols), t
    # and the JSON field bag on profiles never carries an @ in a public value
    for r in con.execute("SELECT fields_json FROM cso_profiles"):
        for k, v in json.loads(r[0]).items():
            if v.get("visibility") == "public":
                assert "@" not in json.dumps(v.get("value")), k


def test_consent_required_fields_are_empty_until_reviewed(con):
    for r in con.execute("SELECT fields_json FROM cso_profiles WHERE is_stand_in=1"):
        for k, v in json.loads(r[0]).items():
            if v["visibility"] == "consent_required":
                assert v["value"] is None, k


def test_unsourced_draft_paragraphs_are_dropped(con):
    pack = drafting.build_evidence_pack(con, "standin-01", None, None)
    d = drafting.Draft(sections=[drafting.Section(title="Summary", paragraphs=[
        drafting.Paragraph(kind="evidence", text="This funder prioritises women-led enterprises.", fact_ids=[]),
        drafting.Paragraph(kind="evidence", text="Made-up fact id.", fact_ids=["F999"]),
        drafting.Paragraph(kind="evidence", text="Real.", fact_ids=[pack["facts"][0]["id"]]),
        drafting.Paragraph(kind="cso_to_fill", text="What changed for whom?"),
    ])])
    kept, dropped = drafting._check(d, pack)
    assert len(dropped) == 2
    assert [p["kind"] for p in kept[0]["paragraphs"]] == ["evidence", "cso_to_fill"]


def test_template_draft_never_invents_evidence(con):
    out = drafting.draft(con, "standin-02", None, 1, use_model=False)
    assert out["mode"] == "template" and out["dropped"] == []
    ids = {f["id"] for f in out["facts"]}
    for s in out["sections"]:
        for p in s["paragraphs"]:
            if p["kind"] == "evidence":
                assert p["fact_ids"] and set(p["fact_ids"]) <= ids


def test_open_match_api_needs_no_personal_data(con):
    m = matching.match(con, matching.MatchInput(themes=["livelihoods"], state_code="AS"), limit=3)
    assert m["matches"] and set(m["input"]) == {"themes", "state_code", "subareas", "districts", "ask_min_lakh", "ask_max_lakh"}
