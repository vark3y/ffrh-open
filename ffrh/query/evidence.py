"""Evidence records: the unit every attribute, match reason and draft claim must carry."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, asdict, field


@dataclass
class Evidence:
    source_id: str
    source_name: str
    publisher: str
    url: str
    retrieved_at: str
    locator: str                 # how to find it again: table filter, row numbers, or page URL
    value: str = ""              # the number or phrase the claim rests on
    source_rows: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["source_rows"] = d["source_rows"][:12]
        return d


_SRC_CACHE: dict[str, sqlite3.Row] = {}


def source_row(con: sqlite3.Connection, source_id: str) -> sqlite3.Row:
    if source_id not in _SRC_CACHE:
        r = con.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
        if r is None:
            raise KeyError(f"unknown source_id {source_id}")
        _SRC_CACHE[source_id] = r
    return _SRC_CACHE[source_id]


def make(con: sqlite3.Connection, source_id: str, locator: str, value: str = "",
         source_rows: list[int] | None = None, url: str | None = None, retrieved_at: str | None = None) -> Evidence:
    s = source_row(con, source_id)
    return Evidence(source_id=source_id, source_name=s["name"], publisher=s["publisher"],
                    url=url or s["url"], retrieved_at=retrieved_at or s["retrieved_at"],
                    locator=locator, value=value, source_rows=list(source_rows or []))


def claim(text: str, ev: Evidence | list[Evidence]) -> dict:
    evs = ev if isinstance(ev, list) else [ev]
    return {"text": text, "evidence": [e.as_dict() for e in evs]}
