"""The source registry. Add a row here before ingesting anything from a new place.

`retrieved_at` is the date the copy we hold was obtained, not the publisher's date.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Source:
    source_id: str
    name: str
    publisher: str
    url: str
    retrieved_at: str
    covers: str = ""
    licence: str = "unstated"
    notes: str = ""
    personal_data: str = "none"


# Retrieval dates for the two bulk files come from the download timestamps of the copies
# in hand (MCA: 2026-05-07, Darpan: 2026-05-17). Re-downloads must update these.
MCA_CSR = Source(
    source_id="mca_csr_portal_2014_24",
    name="National CSR Portal - CSR master data (project level)",
    publisher="Ministry of Corporate Affairs, Government of India",
    url="https://www.csr.gov.in/",
    retrieved_at="2026-05-07",
    covers="FY 2014-15 to FY 2023-24",
    licence="Government Open Data License - India (GODL) as republished by Dataful",
    notes=("Obtained as the Dataful compilation of csr.gov.in data (dataful.in/datasets/1612). "
           "Amounts in INR crore. The project_amount_outlay column is unreliable and is never used for scoring."),
    personal_data="none",
)

NGO_DARPAN = Source(
    source_id="ngo_darpan_grants_2025_01",
    name="NGO Darpan - registered NGOs with year-wise grants",
    publisher="NITI Aayog / NGO Darpan, Government of India",
    url="https://ngodarpan.gov.in/",
    retrieved_at="2026-05-17",
    covers="Grants data as on 30-01-2025",
    licence="Government Open Data License - India (GODL) as republished by Dataful",
    notes=("Obtained as the Dataful compilation (dataful.in/collections/637). The register lists an "
           "email per NGO; this project does NOT store it."),
    personal_data="Raw file contains NGO contact emails (dropped at ingest).",
)

# Stand-in cohort profiles built by this project from the public register, for the demo only.
STAND_IN_COHORT = Source(
    source_id="ffrh_stand_in_cohort",
    name="Stand-in demo cohort (built from NGO Darpan public register)",
    publisher="This project",
    url="https://ngodarpan.gov.in/",
    retrieved_at="2026-09-08",
    covers="Demo only",
    licence="Apache-2.0 (project output)",
    notes="Selected by rule from NGO Darpan: NE-registered NGOs with livelihood-classifiable grant records. "
          "NOT the FFRH cohort. Replace when the FFRH profiles are shared and consent is reviewed.",
    personal_data="none",
)

MANUAL_SIGNAL = Source(
    source_id="manual_logged_signal",
    name="Signal logged by a hub member (with URL)",
    publisher="Hub member entry",
    url="n/a",
    retrieved_at="2026-09-08",
    covers="ongoing",
    licence="n/a",
    notes="A person saw something (a post, a talk, an article) and logged it with the public URL. "
          "Shown with the URL and the date logged. Never scraped.",
    personal_data="May reference named executives in public posts; only the public URL and a one-line note are kept.",
)

CURATED_RFP = Source(
    source_id="curated_rfp",
    name="RFP / call for proposals, fetched from its public page",
    publisher="Issuer (see each RFP)",
    url="n/a",
    retrieved_at="2026-09-08",
    covers="ongoing",
    licence="Issuer's terms; only public text stored, with URL",
    notes="Added one link at a time by a hub member. The public text is fetched and stored with the retrieval date.",
    personal_data="none expected",
)

ALL: list[Source] = [MCA_CSR, NGO_DARPAN, STAND_IN_COHORT, MANUAL_SIGNAL, CURATED_RFP]


def upsert_sources(con: sqlite3.Connection, sources: list[Source] | None = None) -> None:
    for s in sources or ALL:
        d = asdict(s)
        con.execute(
            """INSERT INTO sources(source_id,name,publisher,url,licence,retrieved_at,covers,notes,personal_data)
               VALUES(:source_id,:name,:publisher,:url,:licence,:retrieved_at,:covers,:notes,:personal_data)
               ON CONFLICT(source_id) DO UPDATE SET name=excluded.name, publisher=excluded.publisher,
               url=excluded.url, licence=excluded.licence, retrieved_at=excluded.retrieved_at,
               covers=excluded.covers, notes=excluded.notes, personal_data=excluded.personal_data""",
            d,
        )


def register_feed_source(con: sqlite3.Connection, source_id: str, name: str, publisher: str, url: str,
                         retrieved_at: str, notes: str = "") -> None:
    upsert_sources(con, [Source(source_id=source_id, name=name, publisher=publisher, url=url,
                                retrieved_at=retrieved_at, covers="rolling feed",
                                licence="Publisher's terms; headline, link and short summary only",
                                notes=notes, personal_data="Public news; may name individuals.")])
