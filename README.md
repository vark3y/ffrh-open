# FFRH open funder-intelligence prototype

Open data + query layers, and three persona surfaces, for the Fractional Fund Raising Hub (Node/SeSTA)
concept note. Built for the Guwahati convening demo (October 2026). Not a finished product.

**Two rules the whole build follows**

1. Every funder attribute, match reason and proposal claim shows its **source and retrieval date**. An
   assertion with no source is dropped, not shown.
2. Data protection is assumed to apply and the CSO consent basis is assumed **unreviewed**: fields that need
   consent are empty and flagged; see [DPDP_NOTES.md](DPDP_NOTES.md).

## What is in the box

| Layer | What | Where |
|---|---|---|
| Open data | North East slice of the National CSR Portal (1,176 companies, 6,727 project lines, FY2014-15 to FY2023-24), NGO Darpan NE register (10,710 NGOs, 43,929 grant rows, emails dropped), public news signals, curated RFPs | `data/ffrh.sqlite` built by `scripts/` |
| Open query | funder profiles with evidence, rule-based CSO→funder matching, livelihood sub-area patterns, priority shifts, 80/20 signal feed | `/api/v1/*`, docs at `/docs` |
| Protected | FFRH team board, advisory view, CSO guided flow (profile → sub-areas → funders → RFPs → cited first draft) | `/hub` (demo gate) |

## Run it

```bash
python3.12 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
# put the two raw public files in data/raw/ (see Data below), then:
./.venv/bin/python scripts/build_db.py
./.venv/bin/python scripts/seed_rfps.py      # optional, needs internet
./.venv/bin/python scripts/fetch_news.py     # optional, needs internet
./.venv/bin/uvicorn ffrh.api:app --reload --port 8010
```

Open http://localhost:8010. Protected layer: `/hub/enter`, shared word `ffrh-demo` (change with `FFRH_HUB_TOKEN`).
Persona surfaces are not real access control; they are a demo gate. See `docs/ARCHITECTURE.md`.

## Data

Two public downloads, kept **out** of the repo (`data/raw/` is git-ignored):

- National CSR Portal project ledger, FY2014-15 to FY2023-24 — Ministry of Corporate Affairs, csr.gov.in
  (obtained as the Dataful compilation, dataset 1612). Save as `data/raw/mca_csr_master.csv`.
- NGO Darpan register with year-wise grants (as on 30-01-2025) — NITI Aayog, ngodarpan.gov.in (obtained as the
  Dataful compilation, collection 637). Save as `data/raw/ngo_darpan_grants.csv`.

`ffrh/sources.py` records the retrieval date of the copies used; update it when you re-download.

## First-pass drafts and the model

Drafting uses Claude (`claude-opus-5` by default) through the official SDK. No key is stored in the project.
Either sign in once with the Anthropic CLI (`brew install anthropics/tap/ant`, then `ant auth login`, which
opens a browser to your Claude Console account) or export `ANTHROPIC_API_KEY` in the shell that runs the
server. Without either, the app produces a template draft from evidence alone and says so.

## Tests

```bash
./.venv/bin/pytest -q
```

## Status (2026-09-08)

- The FFRH cohort profiles and funder list have **not** been shared yet. The cohort shown is a **stand-in**
  built from the public register (flagged everywhere) and must be replaced.
- Foundations that do not file CSR (Azim Premji Foundation, Tata Trusts) have no statutory data and are not
  in the funder set yet; they need a sourced dossier each.
- The narrative feed is public RSS only; LinkedIn is manual-log only, by design.

Licence: Apache-2.0 for code; derived data files carry the source attribution in `ffrh/sources.py`.
