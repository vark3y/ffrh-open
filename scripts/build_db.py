"""Build data/ffrh.sqlite from the raw public files. Idempotent; re-run after re-downloading."""
from __future__ import annotations

import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ffrh.db import connect, init_schema  # noqa: E402
from ffrh.sources import upsert_sources  # noqa: E402
from ffrh.ingest import mca_csr, ngo_darpan, cohort  # noqa: E402
from ffrh.config import MCA_CSR_CSV, NGO_DARPAN_CSV  # noqa: E402

if __name__ == "__main__":
    for p in (MCA_CSR_CSV, NGO_DARPAN_CSV):
        if not p.exists():
            sys.exit(f"missing raw file: {p} (see README: Data)")
    con = connect()
    init_schema(con)
    upsert_sources(con)
    t = time.time(); print("MCA CSR:", mca_csr.ingest(con), f"{time.time()-t:.1f}s")
    t = time.time(); print("NGO Darpan:", ngo_darpan.ingest(con), f"{time.time()-t:.1f}s")
    print("Stand-in cohort:", cohort.build(con))
    con.close()
