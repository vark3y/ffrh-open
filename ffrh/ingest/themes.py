"""Theme and sub-area classification. Every classification is a *rule*, and the rule id is
stored beside the result so a reader can see why a project was labelled the way it was.
"""
from __future__ import annotations

import re

# Coarse themes. Keys are our labels; values are Schedule VII sector strings as they appear
# in the National CSR Portal export (matched case-insensitively on a normalised form).
SECTOR_TO_THEME: dict[str, str] = {
    "education": "education",
    "health care": "health",
    "livelihood enhancement projects": "livelihoods",
    "vocational skills": "livelihoods",
    "women empowerment": "women",
    "gender equality": "women",
    "rural development projects": "rural_development",
    "environmental sustainability": "environment",
    "conservation of natural resources": "environment",
    "agro forestry": "environment",
    "animal welfare": "environment",
    "clean ganga fund": "environment",
    "poverty, eradicating hunger, malnutrition": "poverty_nutrition",
    "sanitation": "wash",
    "safe drinking water": "wash",
    "swachh bharat kosh": "wash",
    "training to promote sports": "sports",
    "encouraging sports": "sports",
    "art and culture": "arts_culture",
    "disaster management": "disaster",
    "socio-economic inequalities": "inclusion",
    "socio-economic equalities": "inclusion",
    "armed forces, veterans, war widows/ dependants": "other",
    "setting up homes and hostels for women": "inclusion",
    "setting up orphanage": "inclusion",
    "senior citizens welfare": "inclusion",
    "reducing inequalities": "inclusion",
    "slum area development": "urban",
    "technology incubators": "research_innovation",
    "armed forces, veterans, war widows": "other",
    "prime minister's national relief fund": "other",
    "pm cares fund": "other",
    "other central government funds": "other",
    "nec/ not mentioned": "unstated",
    "any other fund": "other",
}

LIVELIHOOD_FAMILY = {"livelihoods", "women", "rural_development", "poverty_nutrition"}

THEME_LABELS = {
    "education": "Education", "health": "Health", "livelihoods": "Livelihoods & skills",
    "women": "Women's empowerment", "rural_development": "Rural development",
    "environment": "Environment & climate", "poverty_nutrition": "Poverty, hunger & nutrition",
    "wash": "Water & sanitation", "sports": "Sports", "arts_culture": "Arts & culture",
    "disaster": "Disaster management", "inclusion": "Inclusion & social protection",
    "urban": "Urban / slum development", "research_innovation": "Technology & research",
    "other": "Other (funds, relief)", "unstated": "Not stated in filing",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def sector_to_theme(sector: str) -> str:
    n = _norm(sector)
    if n in SECTOR_TO_THEME:
        return SECTOR_TO_THEME[n]
    # loose contains-matching for variants like "Health Care, Preventive Health Care"
    for key, theme in SECTOR_TO_THEME.items():
        if key in n:
            return theme
    return "other"


# Livelihood sub-areas. Each rule: (rule_id, label, compiled regex). First match wins, in order.
SUBAREA_RULES: list[tuple[str, str, re.Pattern]] = [
    ("sub.handloom_craft", "Handloom, handicraft & bamboo",
     re.compile(r"\b(handloom|weav|handicraft|artisan|bamboo|cane\b|eri\b|muga|silk|sericultur|craft)", re.I)),
    ("sub.livestock_fisheries", "Livestock, poultry & fisheries",
     re.compile(r"\b(piggery|pig\b|pigs\b|poultry|dairy|goat|cattle|fisher|aquacultur|fish\b|livestock|animal husbandry|duck)", re.I)),
    ("sub.agri_horti", "Agriculture & horticulture",
     re.compile(r"\b(farm|agri|crop|seed|organic|horticultur|tea garden|orchard|kisan|paddy|irrigat|kitchen garden|mushroom|spice|ginger|turmeric)", re.I)),
    ("sub.skilling", "Skilling & employability",
     re.compile(r"\b(skill|vocational|employab|apprentic|\biti\b|placement|nursing training|driver training|training cent)", re.I)),
    ("sub.shg_enterprise", "SHGs, FPOs & micro-enterprise",
     re.compile(r"\b(shg|self[- ]help|micro[- ]?enterpris|entrepreneur|fpo|producer (company|organi)|cooperativ|micro[- ]?financ|livelihood mission|income generat)", re.I)),
    ("sub.tourism", "Tourism & homestays",
     re.compile(r"\b(touris|homestay|eco[- ]?tourism)", re.I)),
    ("sub.climate_resilient", "Climate-resilient livelihoods",
     re.compile(r"\b(climate|flood|watershed|agro[- ]?forest|solar|renewable|resilien|wetland|erosion)", re.I)),
    ("sub.generic_livelihood", "Livelihood (unspecified)",
     re.compile(r"\b(livelihood|income|rural development|community development)", re.I)),
]

SUBAREA_LABELS = {rid: label for rid, label, _ in SUBAREA_RULES}


def classify_subarea(project_name: str) -> tuple[str | None, str | None]:
    """Return (subarea_id, rule_id) or (None, None)."""
    text = project_name or ""
    for rule_id, _label, rx in SUBAREA_RULES:
        if rx.search(text):
            return rule_id.split(".", 1)[1], rule_id
    return None, None


# NGO Darpan field_of_work is free text and mostly junk ("Nil", "Not received"). We only
# assign a theme when a keyword fires; otherwise NULL, which downstream code treats as unknown.
DARPAN_THEME_RULES: list[tuple[str, re.Pattern]] = [
    ("livelihoods", re.compile(r"livelihood|skill|vocational|employment|income|self[- ]help|shg|entrepreneur|micro ?finance|handloom|weav|handicraft|agri|farm|horticult|piggery|poultry|dairy|fisher|livestock|sericult", re.I)),
    ("women", re.compile(r"women|gender|girl", re.I)),
    ("education", re.compile(r"educat|school|literacy|scholarship|student|teacher", re.I)),
    ("health", re.compile(r"health|medical|hospital|hiv|aids|tb\b|nutrition|sanitation|drinking water|disab", re.I)),
    ("environment", re.compile(r"environment|forest|climate|biodivers|wildlife|conservation|plantation", re.I)),
    ("rural_development", re.compile(r"rural|village|community development|panchayat|tribal|infrastructure", re.I)),
    ("arts_culture", re.compile(r"art|culture|heritage|sport|youth", re.I)),
    ("disaster", re.compile(r"disaster|relief|flood", re.I)),
]

JUNK = re.compile(r"^\s*(nil|na|n/a|none|not (received|applicable|available|yet received|sanctioned|mentioned)|grant not received|-+|\.+)?\s*$", re.I)


def darpan_theme(field_of_work: str) -> str | None:
    t = field_of_work or ""
    if JUNK.match(t):
        return None
    for theme, rx in DARPAN_THEME_RULES:
        if rx.search(t):
            return theme
    return None
