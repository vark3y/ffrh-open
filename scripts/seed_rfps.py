"""Fetch and store the seed RFP pages (public links found 2026-09-08)."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ffrh.db import connect, init_schema
from ffrh.ingest import rfps
con = connect(); init_schema(con)
for r in rfps.seed(con): print(r)
con.close()
