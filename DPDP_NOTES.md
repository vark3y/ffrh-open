# Data protection notes (DPDP Act 2023) — what this design needs consent for

Assumption throughout: the Digital Personal Data Protection Act applies, the consent basis for the
CSO data FFRH has collected has **not** been reviewed, and this project must not widen exposure
while that review is pending. Nothing in this file is legal advice; it is the list a reviewer needs.

## 1. What the open layer holds (no consent needed, but stated)

| Data | Personal data? | What we do |
|---|---|---|
| National CSR Portal project ledger (company, state, district, project, spend) | No. Companies, not people. | Stored in full for the eight NE states. |
| NGO Darpan register (NGO name, id, city, state, grant rows) | The raw file carries an **email per NGO**. | **Email is dropped at ingest and never stored.** Everything else is the public register. |
| Public news RSS items | Articles may name individuals. | Headline, link, date, short summary only; nothing about the person is extracted or indexed. |
| Curated RFP pages | Usually none. | Public text stored with retrieval date; contact names inside an RFP are not extracted. |

## 2. Fields that need a consent basis before they can be loaded (protected layer)

The stand-in cohort has these fields **empty** and marked `consent_required`. When the FFRH cohort
profiles arrive, each of these needs a recorded basis (consent from the CSO, or a documented
legitimate use) before it is loaded, and the basis goes into `fields_json.<field>.consent_basis`.

| Field | Why it needs a basis | Who sees it in this design |
|---|---|---|
| `programme_summary` | CSO's own description shared with FFRH for a different purpose (assessment/mentoring) | CSO itself, FFRH team |
| `current_funders` | Commercially sensitive to the CSO; came via FFRH/Bridgespan spreadsheets and email | CSO itself, FFRH team; **never** advisory or open |
| `annual_budget` / financials | Same, plus proposal open question in the concept note ("who can see CSO financial details") | CSO itself; FFRH team only if the CSO agrees |
| `future_ready_score` | Assessment output about the organisation; sharing it with funders changes its purpose | CSO itself; FFRH team |
| `contact_person` (name, phone, email of staff) | Personal data of an identifiable individual (DPDP s.2(t)); purpose limitation (s.6) | Not loaded at all in the prototype |

Design rule enforced in code: a `consent_required` field with no recorded basis renders as
"withheld — consent not reviewed", is excluded from the drafting evidence pack, and never reaches the
open API.

## 3. Things this design deliberately does not do

- **No LinkedIn scraping** of CSR heads, foundation staff or NGO founders. Executive posts enter the
  narrative feed only when a hub member logs a public URL by hand, with the date they logged it.
- **No people graph.** The Civora warm-referral idea (board members ↔ funder staff) is not built here;
  it would store work histories of people who never consented to this project.
- **No inference about individuals.** "Funder priority shifts" are computed from what the *company*
  filed, never from what a named person said.
- **No cross-source profiling of NGOs beyond the public register.** We do not join Darpan to third-party
  data by name.

## 4. Things a reviewer still has to decide

1. **Fiduciary.** Who is the data fiduciary for the cohort profiles: Node/SeSTA, FFRH, or Tech4Dev? The
   consent notice must name them.
2. **Purpose statement for the CSOs.** The profiles were collected for organisational development and
   fundraising support. Using them to generate matches and drafts is close to that purpose; showing them to
   an *advisory group* may not be. Recommend a fresh, specific consent for the advisory view.
3. **Retention.** Drafts and access logs are stored in the SQLite file. Set a retention period (suggest 12
   months for drafts, 90 days for access logs) before real profiles are loaded.
4. **Funder-side people.** The concept note lists "executive LinkedIn feeds" as a source. That is personal
   data of people who have not consented to this project. Recommend limiting to what companies publish in
   their own filings and press releases, which is what the prototype does.
5. **Open-source publication.** The repository ships derived, non-personal data only. The raw Darpan file
   (with emails) must stay out of the repo and out of any shared drive that is broader than the team.

## 5. Where each rule lives in the code

- Email dropped at ingest: `ffrh/ingest/ngo_darpan.py` (the column is read and never written).
- Consent flags per field: `ffrh/ingest/cohort.py` (`FIELD_TEMPLATE`), rendered in `hub_cso.html`.
- Evidence pack excludes non-consented fields: `ffrh/protected/drafting.py` (`build_evidence_pack`).
- Manual-only signal logging: `ffrh/ingest/news.py` (`log_manual`).
- Access log for the protected layer: `access_log` table, written in `ffrh/api.py`.
- Tests: `tests/test_provenance.py` (`test_no_emails_stored_anywhere`, `test_consent_required_fields_are_empty_until_reviewed`).
