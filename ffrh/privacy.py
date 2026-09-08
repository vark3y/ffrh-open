"""Structured content for the data-protection page.

The full working notes stay in DPDP_NOTES.md, which is the document a reviewer or a lawyer reads.
This module is the same substance arranged for a person who is not either of those: one claim per
section, plain language, the uncomfortable parts stated rather than buried.

Nothing here is legal advice. The whole point of the page is to show what has NOT been settled.
"""
from __future__ import annotations

HEADLINE = "What we do with data, and what we refuse to do with it"
STANDFIRST = ("This prototype is built on public records about companies. It also touches information about "
              "nonprofits and the people who work in them. The Digital Personal Data Protection Act applies to "
              "the second kind, and the consent basis for it has not been reviewed yet. So the design withholds "
              "that data rather than assuming permission.")

SECTIONS = [
    {
        "tag": "The rule",
        "title": "Nothing is asserted without a source and a date",
        "body": [
            "Every funder attribute, every match reason and every sentence in a generated draft carries the source "
            "it came from and the day that source was retrieved. You can open the chip beside any claim and see the "
            "publisher, the link, and the exact rows in the original file.",
            "This is not decoration. An unsourced claim about what a funder wants is worse than no claim, because "
            "someone will repeat it in a real conversation with that funder.",
        ],
        "cards": [],
    },
    {
        "tag": "Company data",
        "title": "The funder side is public record, and stays public",
        "body": [
            "Companies file their corporate social responsibility spending with the Ministry of Corporate Affairs. "
            "That filing names the company, the state, the district, the project and the amount. It is about "
            "organisations, not people, and it is published by the government."
        ],
        "cards": [
            {"h": "What we hold", "p": "The North East slice of the national CSR project ledger, 2014-15 to 2023-24."},
            {"h": "Personal data in it", "p": "None. Companies and amounts, no named individuals."},
            {"h": "What we never infer", "p": "We do not describe what a funder intends or prefers, only what it filed."},
            {"h": "Named individuals", "p": "We build no graph of people at funders, and store no executive profiles."},
        ],
    },
    {
        "tag": "Nonprofit data",
        "title": "We drop the email before we store the row",
        "body": [
            "The public nonprofit register carries a contact email for every organisation. This project reads that "
            "column and discards it. It is never written to the database, never served by the API, and there is an "
            "automated test that fails the build if an email column ever appears in any table.",
            "What we keep from the register is the organisation's name, its registration id, its city and state, and "
            "its grant history. All of it already public, all of it about the organisation rather than a person.",
        ],
        "cards": [],
    },
    {
        "tag": "The unresolved part",
        "title": "Five fields are switched off until someone reviews the consent basis",
        "body": [
            "The hub already holds richer profiles of its cohort: programme descriptions, current funders, budgets, "
            "readiness scores, contact people. Those arrived through spreadsheets and email, collected for mentoring "
            "and assessment. Using them to generate funder matches and proposals is a different purpose, and showing "
            "them to an advisory group is a different audience again.",
            "So they are not loaded. In the prototype each one renders as withheld, is excluded from the evidence a "
            "draft is allowed to use, and never reaches the open API. Turning any of them on is a decision a person "
            "has to record, not a default.",
        ],
        "cards": [
            {"h": "Programme summary", "p": "The organisation's own description, shared with the hub for a different purpose."},
            {"h": "Current funders", "p": "Commercially sensitive to the organisation. Should never reach the advisory view."},
            {"h": "Annual budget and financials", "p": "The concept note itself flags who may see these as an open question."},
            {"h": "Readiness assessment score", "p": "An internal judgement about an organisation. Showing it to funders changes what it is for."},
            {"h": "Named contact person", "p": "Personal data about an identifiable individual. Not loaded at all in this prototype."},
        ],
    },
    {
        "tag": "Signals",
        "title": "No social media scraping, by design",
        "body": [
            "The concept note lists executive posts on professional networks as a data source. Those are personal "
            "data about people who have not agreed to be in this system, and collecting them at scale is a posture "
            "this project deliberately does not adopt.",
            "Instead the news feed reads public RSS feeds of North East dailies and CSR press, keeping only a "
            "headline, a link, a date and a short summary. If someone on the team sees a relevant post, they can log "
            "it by hand with its public link, and it is shown as exactly that.",
        ],
        "cards": [],
    },
    {
        "tag": "Still open",
        "title": "What a reviewer still has to decide",
        "body": ["These are not rhetorical. Each one needs an answer before real cohort data is loaded."],
        "cards": [
            {"h": "Who is the data fiduciary?", "p": "The consent notice has to name whether it is Node/SeSTA, the hub, or Tech4Dev."},
            {"h": "Does the purpose stretch?", "p": "Profiles were collected for organisational development. Matching is close to that. The advisory view may not be."},
            {"h": "How long do we keep things?", "p": "Drafts and access logs currently persist forever. A retention period is suggested but not set."},
            {"h": "Funder-side people", "p": "Limiting to what companies publish themselves is the current position, and should be confirmed."},
        ],
    },
    {
        "tag": "Open source",
        "title": "What ships in the repository, and what never will",
        "body": [
            "The code is Apache-2.0 and public. The derived database can be rebuilt by anyone from the two public "
            "downloads. The raw register file, which contains those contact emails, is excluded from the repository "
            "and should not be circulated more widely than the team.",
        ],
        "cards": [],
    },
]

# Where each promise is actually enforced, so a reader can check rather than trust.
ENFORCEMENT = [
    ("Email dropped at ingest", "ffrh/ingest/ngo_darpan.py", "The column is read and never written."),
    ("Consent flag per field", "ffrh/ingest/cohort.py", "FIELD_TEMPLATE marks each field public or consent_required."),
    ("Withheld fields kept out of drafts", "ffrh/protected/drafting.py", "build_evidence_pack skips anything not consented."),
    ("Unsourced draft text dropped", "ffrh/protected/drafting.py", "_check removes claims whose fact ids do not resolve."),
    ("Manual-only social signals", "ffrh/ingest/news.py", "log_manual is the only path for a post, and needs a public URL."),
    ("Access to the protected layer logged", "ffrh/api.py", "Every protected page view writes to the access_log table."),
    ("Tested, not just promised", "tests/test_provenance.py", "Tests fail if an email column appears or a consent field is populated."),
]
