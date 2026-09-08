"""Curated RFP ingest: one public link at a time. The public text is fetched and stored with the
retrieval date so a CSO can see exactly what the issuer said and when we read it.
No bulk scraping of listing sites."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser

import httpx

from ..sources import CURATED_RFP


class _Text(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "noscript"}

    def __init__(self):
        super().__init__(); self.parts = []; self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self._skip += 1
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div"}: self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip: self._skip -= 1

    def handle_data(self, data):
        if not self._skip: self.parts.append(data)


def fetch_text(url: str, timeout: float = 25.0) -> tuple[str, str]:
    r = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "ffrh-open/0.1"})
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        return "", "pdf"  # text extraction for PDFs is out of scope for the demo; link is kept
    p = _Text(); p.feed(r.text)
    text = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", "".join(p.parts))).strip()
    return text[:20000], "html"


def add(con: sqlite3.Connection, url: str, title: str, issuer: str, deadline: str | None = None,
        states: list[str] | None = None, themes: list[str] | None = None, issuer_cin: str | None = None,
        fetch: bool = True) -> int:
    now = datetime.now(timezone.utc).date().isoformat()
    body, kind = "", "none"
    if fetch:
        try:
            body, kind = fetch_text(url)
        except Exception as e:  # noqa: BLE001
            body, kind = "", f"fetch-failed: {type(e).__name__}"
    cur = con.execute("""INSERT INTO rfps(title,issuer,issuer_cin,url,deadline,states,themes,body_text,retrieved_at,source_id,status)
                         VALUES(?,?,?,?,?,?,?,?,?,?,'open')
                         ON CONFLICT(url) DO UPDATE SET title=excluded.title, issuer=excluded.issuer, deadline=excluded.deadline,
                         states=excluded.states, themes=excluded.themes, body_text=excluded.body_text, retrieved_at=excluded.retrieved_at""",
                      (title, issuer, issuer_cin, url, deadline, json.dumps(states or []), json.dumps(themes or []),
                       (body or "") + ("" if kind == "html" else f"\n[no text stored: {kind}]"), now, CURATED_RFP.source_id))
    con.commit()
    return cur.lastrowid


# Seed list found by a web search on 2026-09-08. Each is a public page; deadlines as stated on the page at that date.
SEED = [
    dict(url="https://ngobox.org/full_rfp_eoi_ToR---Implementation-Partnership-for-Climate-Resilient-Livelihood-Strengthening-and-Community-Capacity-Building-in-Nagaland-SELCO-Foundation_19825",
         title="Implementation partnership: climate-resilient livelihood strengthening and community capacity building in Nagaland",
         issuer="SELCO Foundation", deadline="2026-09-12", states=["NL"], themes=["livelihoods", "women", "environment"]),
    dict(url="https://ngobox.org/full_rfp_eoi_Terms-of-Reference-(TOR)-for-Project-Consultant---Organization-%E2%80%93-DRE-Assessment-&-Coordination-Support-for-Common-Facility-Centres-(CFCs)-SELCO-Foundation_19831",
         title="ToR: DRE assessment and coordination support for Common Facility Centres (Assam, Meghalaya, Mizoram)",
         issuer="SELCO Foundation", deadline="2026-09-16", states=["AS", "ML", "MZ"], themes=["livelihoods", "environment"]),
    dict(url="https://www2.fundsforngos.org/community-development-2/sbi-foundation-climate-smart-livelihoods-programme-india/",
         title="SBI Foundation: Climate Smart Livelihoods Programme (North East focus)",
         issuer="SBI Foundation", deadline=None, states=["AR", "AS", "MN", "ML", "MZ", "NL", "SK"], themes=["livelihoods", "environment"]),
    dict(url="https://www.ngobox.org/full_rfp_eoi_Expression-of-Interest-(EOI)-for-Trade-&-Livelihood-Partners-BharatCares_19828",
         title="EOI: Trade and livelihood partners (bamboo, Warli, tailoring)",
         issuer="BharatCares", deadline=None, states=[], themes=["livelihoods"]),
    dict(url="https://moef.gov.in/storage/tender/1787320244.pdf",
         title="GEF Small Grants Programme OP8: community grants RFP (RFP/SGPOP8/IND-2026-1)",
         issuer="MoEFCC / UNDP GEF SGP India", deadline=None, states=[], themes=["environment", "livelihoods"]),
    dict(url="https://www2.fundsforngos.org/latest-funds-for-ngos/rfps-strengthening-upscaling-and-nurturing-innovations-for-livelihood-programme-india/",
         title="DST SEED: Strengthening, Upscaling and Nurturing Innovations for Livelihood programme",
         issuer="Department of Science & Technology (SEED division)", deadline=None, states=[], themes=["livelihoods", "research_innovation"]),
]


def seed(con: sqlite3.Connection) -> list[dict]:
    out = []
    for s in SEED:
        rid = add(con, **s)
        r = con.execute("SELECT rfp_id, title, LENGTH(body_text) n, retrieved_at FROM rfps WHERE url=?", (s["url"],)).fetchone()
        out.append(dict(r))
    return out
