"""Hand-written metadata for the open API reference page.

Kept as plain data so the docs page is readable by NGO staff and researchers, not only developers.
The generated OpenAPI schema still lives at /docs and /openapi.json for people who want it.
"""
from __future__ import annotations

BASE = "http://localhost:8010"

INTRO = {
    "title": "Open API",
    "blurb": ("The data layer and the query layer are open. Everything below is public, needs no key and no "
              "account, and returns JSON. Every record carries the source it came from and the date that source "
              "was retrieved."),
    "auth": "No authentication. No rate limit in the prototype. Please cache rather than hammer it.",
}

# The index table: what you can ask for, in one screen. Modelled on USAspending's endpoint index.
ENDPOINTS = [
    {
        "id": "funders",
        "method": "GET",
        "path": "/api/v1/funders",
        "summary": "Search companies that filed CSR spend in the eight North East states.",
        "plain": "Use this to get the list behind the Funders page: who spent, how much, over how many states.",
        "params": [
            ("q", "string", False, "Match on company name, case-insensitive substring."),
            ("state", "string", False, "One of AR, AS, MN, ML, MZ, NL, SK, TR. Limits to funders with spend filed in that state."),
            ("theme", "string", False, "A theme id from /api/v1/themes, e.g. livelihoods."),
            ("limit", "integer", False, "Default 50, maximum 200."),
            ("offset", "integer", False, "For paging through results."),
        ],
        "example": "/api/v1/funders?state=ML&theme=livelihoods&limit=3",
        "response": """[
  {
    "cin": "L65190MH1994PLC080618",
    "name": "HDFC BANK LIMITED",
    "is_ne_registered": 0,
    "ne_spent_cr_all": 124.19,
    "ne_spent_cr_recent": 106.75,
    "projects": 85,
    "states": 6,
    "last_fy": "2023-24"
  }
]""",
    },
    {
        "id": "funder",
        "method": "GET",
        "path": "/api/v1/funders/{cin}",
        "summary": "One company's full North East profile, with evidence attached to every claim.",
        "plain": ("This is the endpoint that carries the project's core promise. Each item under attributes is a "
                  "sentence plus the source, the retrieval date and the exact rows in the raw file it rests on."),
        "params": [("cin", "string", True, "The Corporate Identification Number, the company's statutory id.")],
        "example": "/api/v1/funders/L65190MH1994PLC080618",
        "response": """{
  "cin": "L65190MH1994PLC080618",
  "name": "HDFC BANK LIMITED",
  "attributes": [
    {
      "text": "Spent \\u20b962.37 crore in Assam (FY22-24), districts: Nagaon, Nalbari, ...",
      "evidence": [{
        "source_id": "mca_csr_portal_2014_24",
        "source_name": "National CSR Portal - CSR master data (project level)",
        "publisher": "Ministry of Corporate Affairs, Government of India",
        "url": "https://www.csr.gov.in/",
        "retrieved_at": "2026-05-07",
        "locator": "csr_projects where cin=..., state_code=AS",
        "source_rows": [118422, 118423]
      }]
    }
  ],
  "by_fy": [], "by_state": [], "by_theme": [], "projects": [],
  "caveats": ["Amounts are what the company reported ..."]
}""",
    },
    {
        "id": "match",
        "method": "POST",
        "path": "/api/v1/match",
        "summary": "Score every funder against a nonprofit's themes, state and sub-areas.",
        "plain": ("The matching engine. It needs nothing personal: themes, a state, optionally sub-areas, districts "
                  "and an ask range. Each match comes back with the reasons that produced its score, each reason "
                  "carrying its own source."),
        "params": [
            ("themes", "string[]", True, "Theme ids, e.g. [\"livelihoods\", \"women\"]."),
            ("state_code", "string", True, "AR, AS, MN, ML, MZ, NL, SK or TR."),
            ("subareas", "string[]", False, "e.g. [\"handloom_craft\", \"skilling\"]."),
            ("districts", "string[]", False, "District names as filed, e.g. [\"East Khasi Hills\"]."),
            ("ask_min_lakh", "number", False, "Advisory only. Compared against the funder's typical project size."),
            ("ask_max_lakh", "number", False, "Advisory only."),
            ("limit", "integer", False, "Default 15."),
        ],
        "body": """{
  "themes": ["livelihoods"],
  "state_code": "ML",
  "subareas": ["handloom_craft"],
  "limit": 3
}""",
        "example": "/api/v1/match",
        "response": """{
  "weights": {"theme": 25, "state": 20, "district": 10, "subarea": 10,
              "agency": 10, "recency": 10, "scale": 10, "signal": 5},
  "candidates": 668,
  "matches": [{
    "cin": "...", "name": "STAR CEMENT MEGHALAYA LIMITED",
    "score": 64.6, "max_score": 100,
    "ne_recent_cr": 5.73,
    "median_project_lakh": 12.0,
    "reasons": [{"text": "Spent \\u20b91.20 crore in Meghalaya in FY22-24 ...",
                 "evidence": [{"source_id": "mca_csr_portal_2014_24", "retrieved_at": "2026-05-07"}]}]
  }],
  "method": "Rule-based score over filed CSR spend FY2021-22 to FY2023-24 ..."
}""",
    },
    {
        "id": "landscape",
        "method": "GET",
        "path": "/api/v1/landscape",
        "summary": "National and North East totals by year, plus spend by state and by theme.",
        "plain": "The numbers behind the Patterns page, including the North East's share of national CSR spend.",
        "params": [],
        "example": "/api/v1/landscape",
        "response": """{
  "national": [{"fy": "2023-24", "national_cr": 33118.0, "ne_cr": 713.1,
                "national_companies": 24390, "ne_share_pct": 2.15}],
  "by_state_fy": [{"fy": "2023-24", "state_code": "AS", "cr": 486.96, "funders": 256}],
  "by_theme_fy": [{"fy": "2023-24", "theme": "health", "cr": 271.02, "funders": 96}],
  "funders_over_1cr_recent": 136
}""",
    },
    {
        "id": "subareas",
        "method": "GET",
        "path": "/api/v1/subareas",
        "summary": "Which livelihood sub-areas actually receive funding, with worked examples.",
        "plain": ("Sub-areas are assigned by keyword rules on the project name as filed. The rule that fired is "
                  "stored on every row, so a classification can always be checked."),
        "params": [("state", "string", False, "Limit to one state. Omit for all eight.")],
        "example": "/api/v1/subareas?state=ML",
        "response": """{
  "state_code": "ML",
  "subareas": [{
    "subarea": "handloom_craft", "label": "Handloom, handicraft & bamboo",
    "recent_cr": 0.01, "recent_funders": 1, "recent_n": 1,
    "top_funders": [{"name": "...", "cin": "...", "cr": 0.01}],
    "examples": [{"project_name": "Bamboo craft training", "fy": "2023-24",
                  "subarea_rule": "sub.handloom_craft", "source_row": 411203}],
    "evidence": {"source_id": "mca_csr_portal_2014_24", "retrieved_at": "2026-05-07"}
  }],
  "unclassified": {"cr": 683.6, "n": 1181},
  "method": "Sub-areas are assigned by keyword rules on the project name as filed ..."
}""",
    },
    {
        "id": "ngos",
        "method": "GET",
        "path": "/api/v1/ngos",
        "summary": "North East nonprofits on the public register, with how many grant rows each has.",
        "plain": ("From NGO Darpan. The register carries an email per organisation; this project drops it at ingest "
                  "and never stores it."),
        "params": [
            ("q", "string", False, "Match on organisation name."),
            ("state", "string", False, "Two-letter state code."),
            ("limit", "integer", False, "Default 50, maximum 200."),
        ],
        "example": "/api/v1/ngos?state=NL&limit=3",
        "response": """[
  {
    "darpan_id": "NL/2017/0169712",
    "name": "NORTH EAST INITIATIVE DEVELOPMENT AGENCY",
    "state_code": "NL", "city": "Kohima",
    "grant_rows": 34, "themes": "livelihoods,education",
    "source_id": "ngo_darpan_grants_2025_01"
  }
]""",
    },
    {
        "id": "signals",
        "method": "GET",
        "path": "/api/v1/signals",
        "summary": "Public news items, split into funding signals and broader narrative.",
        "plain": ("Public RSS feeds of North East dailies and CSR press. Headline, link, date and a short summary "
                  "only. No social media scraping."),
        "params": [
            ("state", "string", False, "Limit to items mentioning that state."),
            ("limit", "integer", False, "Default 60. Split 80% funding, 20% narrative."),
        ],
        "example": "/api/v1/signals?state=AS&limit=10",
        "response": """{
  "funding": [{"title": "...", "url": "https://...", "published_at": "2026-09-07",
               "retrieved_at": "2026-09-08", "source_name": "EastMojo (RSS feed)",
               "funders": ["OIL INDIA LIMITED"], "states": ["AS"], "entry_kind": "auto"}],
  "narrative": [],
  "counts": {"funding": 1, "narrative": 91},
  "method": "Public RSS feeds only ..."
}""",
    },
    {
        "id": "shifts",
        "method": "GET",
        "path": "/api/v1/signals/priority-shifts",
        "summary": "Funders whose mix of themes moved between FY2021-22 and FY2023-24.",
        "plain": ("Computed from what each company filed, never from what a person said. A shift of 25 points or "
                  "more in a theme's share of that company's North East spend."),
        "params": [],
        "example": "/api/v1/signals/priority-shifts",
        "response": """[
  {"cin": "...", "name": "AXIS BANK LIMITED", "ne_cr_2023_24": 85.01,
   "shifts": [{"theme": "education", "share_2021_22": 0.0, "share_2023_24": 0.93}]}
]""",
    },
    {
        "id": "rfps",
        "method": "GET",
        "path": "/api/v1/rfps",
        "summary": "Open calls for proposals, added one public link at a time.",
        "plain": "Curated by hand. The public text of each page is fetched and stored with the date it was read.",
        "params": [],
        "example": "/api/v1/rfps",
        "response": """[
  {"rfp_id": 1, "title": "Implementation partnership: climate-resilient livelihood ...",
   "issuer": "SELCO Foundation", "url": "https://ngobox.org/...",
   "deadline": "2026-09-12", "states": "[\\"NL\\"]", "themes": "[\\"livelihoods\\"]",
   "retrieved_at": "2026-09-08", "status": "open"}
]""",
    },
    {
        "id": "sources",
        "method": "GET",
        "path": "/api/v1/sources",
        "summary": "The source registry. Every record in the API points at one of these.",
        "plain": "Start here if you want to know where anything came from, or whether it contains personal data.",
        "params": [],
        "example": "/api/v1/sources",
        "response": """[
  {"source_id": "mca_csr_portal_2014_24",
   "name": "National CSR Portal - CSR master data (project level)",
   "publisher": "Ministry of Corporate Affairs, Government of India",
   "url": "https://www.csr.gov.in/", "retrieved_at": "2026-05-07",
   "covers": "FY 2014-15 to FY 2023-24",
   "licence": "Government Open Data License - India (GODL) ...",
   "personal_data": "none"}
]""",
    },
    {
        "id": "themes",
        "method": "GET",
        "path": "/api/v1/themes",
        "summary": "The controlled vocabulary: themes, livelihood sub-areas and state codes.",
        "plain": "Look up the ids you need for the filters on every other endpoint.",
        "params": [],
        "example": "/api/v1/themes",
        "response": """{
  "themes": {"livelihoods": "Livelihoods & skills", "health": "Health", "...": "..."},
  "livelihood_subareas": {"handloom_craft": "Handloom, handicraft & bamboo", "...": "..."},
  "livelihood_family": ["livelihoods", "poverty_nutrition", "rural_development", "women"],
  "states": {"AS": "Assam", "ML": "Meghalaya", "...": "..."}
}""",
    },
]

RECIPES = [
    {"q": "Which funders already spend on livelihoods in Meghalaya?",
     "call": "GET /api/v1/funders?state=ML&theme=livelihoods"},
    {"q": "What has this company actually filed in the North East?",
     "call": "GET /api/v1/funders/{cin}"},
    {"q": "Who should a Nagaland handloom organisation talk to?",
     "call": "POST /api/v1/match with state_code NL and subareas [\"handloom_craft\"]"},
    {"q": "Is the North East's share of national CSR spend going up?",
     "call": "GET /api/v1/landscape, then read national[].ne_share_pct"},
    {"q": "Where did a given number come from?",
     "call": "GET /api/v1/sources, then match on the source_id carried by the record"},
]
