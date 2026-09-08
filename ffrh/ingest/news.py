"""Narrative and funding signals from public RSS feeds of North East dailies and CSR press.

Rules: headline, link, published date and a short summary only; retrieval date stamped on every
item; items kept only when they mention a known NE CSR funder, CSR/grant language, or an NE state.
No LinkedIn. Executive posts enter only via the manual logging route (entry_kind='manual').
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

import feedparser
import httpx

from ..sources import register_feed_source

FEEDS = [
    ("feed_eastmojo", "EastMojo", "EastMojo", "https://www.eastmojo.com/feed/"),
    ("feed_morung", "The Morung Express", "The Morung Express, Dimapur", "https://morungexpress.com/feed"),
    ("feed_assamtribune", "The Assam Tribune", "The Assam Tribune, Guwahati", "https://assamtribune.com/feed"),
    ("feed_sentinel", "The Sentinel", "The Sentinel, Guwahati", "https://www.sentinelassam.com/feed"),
    ("feed_nenow", "NorthEast Now", "NorthEast Now", "https://nenow.in/feed"),
    ("feed_shillongtimes", "The Shillong Times", "The Shillong Times", "https://theshillongtimes.com/feed/"),
    ("feed_csrjournal", "The CSR Journal", "The CSR Journal", "https://thecsrjournal.in/feed/"),
]

STATE_RX = {
    "AR": re.compile(r"\bArunachal\b", re.I), "AS": re.compile(r"\bAssam\b|\bGuwahati\b", re.I),
    "MN": re.compile(r"\bManipur\b|\bImphal\b", re.I), "ML": re.compile(r"\bMeghalaya\b|\bShillong\b", re.I),
    "MZ": re.compile(r"\bMizoram\b|\bAizawl\b", re.I), "NL": re.compile(r"\bNagaland\b|\bKohima\b|\bDimapur\b", re.I),
    "SK": re.compile(r"\bSikkim\b|\bGangtok\b", re.I), "TR": re.compile(r"\bTripura\b|\bAgartala\b", re.I),
}
NE_RX = re.compile(r"north[- ]?east", re.I)
FUNDING_RX = re.compile(r"\bCSR\b|corporate social|foundation|grant|MoU|funds?\b|funded|sanction|philanthrop|donat|invest|scheme|skill(ing)?\b|livelihood|self[- ]help|SHG|entrepreneur", re.I)
STRONG_FUNDING_RX = re.compile(r"\bCSR\b|corporate social responsibility|\bgrants?\b|\bgranted\b|\bMoU\b|sanction(ed|s)?\b|philanthrop|\bfoundation(?! day| stone)\b|(crore|lakh)[^.]{0,60}\b(project|fund|scheme|livelihood|skill|SHG|women|farmer|entrepreneur)", re.I)
THEME_RX = {
    "livelihoods": re.compile(r"livelihood|skill|employment|entrepreneur|SHG|self[- ]help|handloom|weav|farmer|agri|piggery|poultry|fisher", re.I),
    "women": re.compile(r"\bwomen\b|gender|girl", re.I),
    "education": re.compile(r"school|education|student|scholarship", re.I),
    "health": re.compile(r"health|hospital|medical|nutrition", re.I),
    "environment": re.compile(r"climate|flood|forest|environment|wildlife|erosion", re.I),
    "disaster": re.compile(r"flood|landslide|disaster|relief", re.I),
}
SUFFIX_RX = re.compile(r"\b(LIMITED|LTD|PRIVATE|PVT|CORPORATION|COMPANY|CO|OF INDIA|INDIA)\b\.?", re.I)
MANUAL_ALIASES = {  # short names the press actually uses; map to the filed company name fragment
    "ONGC": "OIL AND NATURAL GAS CORPORATION", "NRL": "NUMALIGARH REFINERY", "IOCL": "INDIAN OIL CORPORATION",
    "Indian Oil": "INDIAN OIL CORPORATION", "Oil India": "OIL INDIA", "OIL": "OIL INDIA", "NHPC": "NHPC",
    "NEEPCO": "NORTH EASTERN ELECTRIC POWER", "PowerGrid": "POWER GRID CORPORATION", "Power Grid": "POWER GRID CORPORATION",
    "HDFC Bank": "HDFC BANK", "ICICI Bank": "ICICI BANK", "Axis Bank": "AXIS BANK", "SBI": "STATE BANK OF INDIA",
    "Coal India": "COAL INDIA", "NTPC": "NTPC", "GAIL": "GAIL", "BPCL": "BHARAT PETROLEUM", "HPCL": "HINDUSTAN PETROLEUM",
    "Tata Steel": "TATA STEEL", "Tata Power": "TATA POWER", "Star Cement": "STAR CEMENT", "Dalmia": "DALMIA",
    "Assam Gas": "ASSAM GAS", "Numaligarh": "NUMALIGARH REFINERY", "Bandhan Bank": "BANDHAN BANK",
    "Vedanta": "VEDANTA", "Hindalco": "HINDALCO", "Infosys": "INFOSYS", "Wipro": "WIPRO", "NEDFi": "NORTH EASTERN DEVELOPMENT FINANCE",
    "Sikkim Urja": "SIKKIM URJA", "REC": "RURAL ELECTRIFICATION CORPORATION", "Piramal": "PIRAMAL",
}


def _funder_index(con: sqlite3.Connection) -> list[tuple[re.Pattern, str]]:
    idx = []
    names = {r["cin"]: r["name"] for r in con.execute("SELECT cin, name FROM funders")}
    # aliases first
    for alias, frag in MANUAL_ALIASES.items():
        cins = [c for c, n in names.items() if frag in n.upper()]
        if cins:
            idx.append((re.compile(r"\b" + re.escape(alias) + r"\b", re.I), cins[0]))
    # then full names stripped of suffixes, only if >= 2 words (avoid 'ASSAM' matching everything)
    for cin, n in names.items():
        core = SUFFIX_RX.sub("", n).strip(" .,")
        core = re.sub(r"\s+", " ", core)
        if len(core.split()) >= 2 and len(core) >= 10:
            idx.append((re.compile(r"\b" + re.escape(core) + r"\b", re.I), cin))
    return idx


def _classify(text: str, idx) -> tuple[list[str], list[str], list[str], bool]:
    cins = sorted({cin for rx, cin in idx if rx.search(text)})
    states = [sc for sc, rx in STATE_RX.items() if rx.search(text)]
    themes = [t for t, rx in THEME_RX.items() if rx.search(text)]
    funding = (bool(cins) and bool(FUNDING_RX.search(text))) or bool(STRONG_FUNDING_RX.search(text))
    return cins, states, themes, funding


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def fetch_all(con: sqlite3.Connection, timeout: float = 20.0) -> dict:
    now = datetime.now(timezone.utc).date().isoformat()
    idx = _funder_index(con)
    stats = {}
    for sid, name, publisher, url in FEEDS:
        register_feed_source(con, sid, f"{name} (RSS feed)", publisher, url, now,
                             notes="Headline, link, date and a short summary are stored; nothing else.")
        try:
            r = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "ffrh-open/0.1"})
            d = feedparser.parse(r.text)
        except Exception as e:  # noqa: BLE001
            stats[sid] = f"error: {type(e).__name__}"
            continue
        kept = 0
        for e in d.entries:
            title = _strip_html(e.get("title", ""))
            summary = _strip_html(e.get("summary", ""))[:600]
            link = e.get("link")
            if not (title and link):
                continue
            text = f"{title}. {summary}"
            cins, states, themes, funding = _classify(text, idx)
            is_ne = bool(states) or bool(NE_RX.search(text)) or sid != "feed_csrjournal"
            # NE dailies: keep only development-relevant items (theme or funding language); CSR journal: keep only NE items
            if sid == "feed_csrjournal":
                if not (states or NE_RX.search(text)):
                    continue
            elif not (themes or funding or cins):
                continue
            if not is_ne:
                continue
            pub = e.get("published") or e.get("updated")
            try:
                pub_iso = datetime(*e.published_parsed[:6]).date().isoformat() if e.get("published_parsed") else pub
            except Exception:  # noqa: BLE001
                pub_iso = pub
            con.execute("""INSERT OR IGNORE INTO narrative_items(source_id,url,title,published_at,retrieved_at,summary,
                           signal_type,funder_cins,states,themes,entry_kind) VALUES(?,?,?,?,?,?,?,?,?,?,'auto')""",
                        (sid, link, title, pub_iso, now, summary, "funding" if funding else "narrative",
                         json.dumps(cins), json.dumps(states), json.dumps(themes)))
            kept += 1
        stats[sid] = f"{kept}/{len(d.entries)} kept"
    con.commit()
    return stats


def log_manual(con: sqlite3.Connection, url: str, title: str, note: str, states: list[str], themes: list[str],
               funder_cins: list[str], signal_type: str = "funding") -> int:
    now = datetime.now(timezone.utc).date().isoformat()
    cur = con.execute("""INSERT INTO narrative_items(source_id,url,title,published_at,retrieved_at,summary,signal_type,
                         funder_cins,states,themes,entry_kind) VALUES('manual_logged_signal',?,?,?,?,?,?,?,?,?,'manual')""",
                      (url, title, now, now, note, signal_type, json.dumps(funder_cins), json.dumps(states), json.dumps(themes)))
    con.commit()
    return cur.lastrowid
