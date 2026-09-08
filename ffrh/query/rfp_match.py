"""Match live RFPs to a CSO profile: state coverage, theme overlap, keyword hits in the RFP text."""
from __future__ import annotations

import json
import re
import sqlite3

from ..ingest.themes import THEME_LABELS
from . import evidence as ev

KEYWORDS = {
    "livelihoods": ["livelihood", "skill", "income", "enterprise", "farmer", "SHG", "self-help", "women-led"],
    "women": ["women", "gender", "girls"],
    "environment": ["climate", "resilien", "renewable", "solar", "natural resource"],
    "education": ["school", "education", "learning"],
    "health": ["health", "nutrition"],
}


def match_rfps(con: sqlite3.Connection, cso_id: str) -> dict | None:
    c = con.execute("SELECT * FROM cso_profiles WHERE cso_id=?", (cso_id,)).fetchone()
    if not c:
        return None
    themes = json.loads(c["themes"]); state = c["state_code"]
    out = []
    for r in con.execute("SELECT * FROM rfps WHERE status='open' ORDER BY deadline IS NULL, deadline"):
        st = json.loads(r["states"] or "[]"); th = json.loads(r["themes"] or "[]")
        score, reasons = 0, []
        src_kw = dict(source_id=r["source_id"], locator=f"rfps.url", url=r["url"], retrieved_at=r["retrieved_at"])
        if not st:
            score += 20; reasons.append(ev.claim("Open nationally (no state restriction stated on the page)", ev.make(con, **src_kw)))
        elif state in st:
            score += 40; reasons.append(ev.claim(f"Explicitly covers {state} (states named on the page: {', '.join(st)})", ev.make(con, **src_kw, value=", ".join(st))))
        else:
            reasons.append(ev.claim(f"Does not cover {state} (states named: {', '.join(st)})", ev.make(con, **src_kw)))
        ov = [t for t in themes if t in th]
        if ov:
            score += 30; reasons.append(ev.claim(f"Theme overlap: {', '.join(THEME_LABELS[t] for t in ov)}", ev.make(con, **src_kw)))
        body = r["body_text"] or ""
        hits = []
        for t in themes:
            for k in KEYWORDS.get(t, []):
                m = re.search(r"[^.\n]{0,80}" + re.escape(k) + r"[^.\n]{0,80}", body, re.I)
                if m:
                    hits.append((k, m.group(0).strip()))
        if hits:
            score += min(30, 6 * len(hits))
            reasons.append(ev.claim(f"RFP text mentions: {', '.join(k for k, _ in hits[:5])}",
                                    ev.make(con, **src_kw, value=" | ".join(q for _, q in hits[:3]))))
        if not body.strip() or body.startswith("[no text stored"):
            reasons.append(ev.claim("Only the link is stored (PDF or fetch failed); read the source page before relying on this.", ev.make(con, **src_kw)))
        out.append({"rfp_id": r["rfp_id"], "title": r["title"], "issuer": r["issuer"], "url": r["url"], "deadline": r["deadline"],
                    "retrieved_at": r["retrieved_at"], "score": score, "reasons": reasons, "has_text": bool(body.strip()) and not body.startswith("[no text")})
    out.sort(key=lambda x: -x["score"])
    return {"cso_id": cso_id, "display_name": c["display_name"], "rfps": out}
