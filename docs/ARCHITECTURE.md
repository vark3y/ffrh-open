# Architecture

Three layers, exactly as the concept note draws them, in one small Python codebase.

```
raw public files (not in repo)         data/raw/*.csv  (MCA CSR portal, NGO Darpan)
        │  scripts/build_db.py, scripts/fetch_news.py, scripts/seed_rfps.py
        ▼
OPEN DATA LAYER      data/ffrh.sqlite  — sources · funders · csr_projects · national_totals · ngos ·
                                         ngo_grants · narrative_items · rfps
        │  ffrh/query/*   (pure functions over SQLite; every output carries Evidence)
        ▼
OPEN QUERY LAYER     /api/v1/*  (FastAPI, OpenAPI docs at /docs) + public pages /funders /patterns /sources
        │
        ▼
PROTECTED LAYER      /hub/*  — cso_profiles · drafts · access_log; persona surfaces (team / advisory / cso);
                     ffrh/protected/drafting.py (model or template, citations enforced)
```

## Provenance model
`ffrh/query/evidence.py` defines `Evidence(source_id, source_name, publisher, url, retrieved_at, locator, value, source_rows)`.
Every attribute (`funders.profile`), match reason (`matching.match`), sub-area claim (`subareas.attractiveness`),
RFP reason (`rfp_match`) and draft paragraph carries one or more. The `sources` table is the registry;
`ffrh/sources.py` is the only place a source is defined.

## Matching
Deterministic rule score (see `WEIGHTS` in `ffrh/query/matching.py`): theme 25, state 20, district 10,
sub-area 10, agency routing 10, latest-year activity 10, scale 10, logged funding signal 5. It ranks the
plausibility of a *conversation*, not the odds of a grant, and says so on every page.

## Drafting
The model only sees an evidence pack (numbered facts with source + retrieval date). Output is structured
(sections → paragraphs tagged `evidence` with fact ids, or `cso_to_fill` questions). A post-check drops any
`evidence` paragraph whose fact ids are missing or unknown and lists it under "dropped". With no model
credentials the same structure is produced from evidence alone.

## Why SQLite + FastAPI
Runs offline on a laptop in Guwahati, one file to back up, `sqlite3` CLI to inspect, no accounts to create.
Swapping the store for Postgres later is a `db.py` change; the query functions do not care.

## Not built (on purpose)
LinkedIn ingestion, people graphs, bulk scraping of RFP listing sites, foundation (non-statutory) funder data
(needs the FFRH funder list + annual-report extraction, each with a source line).
