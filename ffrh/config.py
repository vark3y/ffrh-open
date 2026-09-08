"""Project-wide configuration. No secrets live here; see .env.example."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DERIVED_DIR = DATA_DIR / "derived"
DB_PATH = Path(os.environ.get("FFRH_DB", DATA_DIR / "ffrh.sqlite"))

# The eight North Eastern states as spelt in the MCA CSR portal and NGO Darpan exports.
NE_STATES: dict[str, str] = {
    "ARUNACHAL PRADESH": "AR",
    "ASSAM": "AS",
    "MANIPUR": "MN",
    "MEGHALAYA": "ML",
    "MIZORAM": "MZ",
    "NAGALAND": "NL",
    "SIKKIM": "SK",
    "TRIPURA": "TR",
}

# Raw source files. Both are public-data downloads; they are NOT committed to the repo.
# Paths can be overridden with env vars so contributors can point at their own copies.
MCA_CSR_CSV = Path(os.environ.get("FFRH_MCA_CSV", RAW_DIR / "mca_csr_master.csv"))
NGO_DARPAN_CSV = Path(os.environ.get("FFRH_DARPAN_CSV", RAW_DIR / "ngo_darpan_grants.csv"))

# Protected-layer demo access. This is a demo gate, not a security boundary.
HUB_TOKEN = os.environ.get("FFRH_HUB_TOKEN", "ffrh-demo")

# Model used for proposal drafting. Credentials resolve via the Anthropic SDK's normal
# chain (ANTHROPIC_API_KEY, or an `ant auth login` profile). If none is present the app
# falls back to an evidence-only template draft so the demo never blocks on a key.
DRAFT_MODEL = os.environ.get("FFRH_DRAFT_MODEL", "claude-opus-5")
