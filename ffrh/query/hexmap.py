"""Hex tile cartogram of the eight North East states.

A true geographic map wastes space here: Assam sprawls, Sikkim and Tripura almost vanish, and the
reader ends up comparing land area instead of money. One hexagon per state fixes that.

Geometry is flat-top hexagons on an odd-q offset grid, the convention used by the NPR, Datawrapper
and UK election tile maps:

    flat-top vertex i (i = 0..5):  angle = 60 * i degrees
                                   x = cx + R * cos(angle),  y = cy + R * sin(angle)
    odd-q offset placement:        x = R * 1.5 * col
                                   y = R * sqrt(3) * (row + 0.5 * (col % 2))

Colour is binned on a log scale, not continuous. Assam files roughly six times the spend of the next
state, so a linear ramp would crush the other seven into one indistinguishable shade. The rupee
figure is printed inside every tile, so nothing depends on colour alone.
"""
from __future__ import annotations

import math
import sqlite3

# (row, col) on the odd-q grid. Column 1 is deliberately empty: it reads as the Siliguri corridor
# that separates Sikkim from the other seven states.
LAYOUT: dict[str, tuple[int, int]] = {
    "AR": (0, 2),
    "SK": (1, 0), "AS": (1, 2), "NL": (1, 3),
    "ML": (2, 2), "MN": (2, 3),
    "TR": (3, 2), "MZ": (3, 3),
}

STATE_NAMES = {"AR": "Arunachal Pradesh", "AS": "Assam", "MN": "Manipur", "ML": "Meghalaya",
               "MZ": "Mizoram", "NL": "Nagaland", "SK": "Sikkim", "TR": "Tripura"}

# Sequential ramp, pale to the project's indigo. Colour-blind safe: it varies in lightness only.
RAMP = ["#eceaf6", "#c9cbe6", "#9ea3d1", "#6a72b4", "#33418f"]


def _polygon(cx: float, cy: float, r: float) -> str:
    pts = []
    for i in range(6):
        a = math.radians(60 * i)
        pts.append(f"{cx + r * math.cos(a):.2f},{cy + r * math.sin(a):.2f}")
    return " ".join(pts)


def _bins(values: list[float], n: int = 5) -> list[float]:
    """Break points on a log scale, returned as real rupee amounts.

    Quantile breaks fail badly here: with only eight states, the top two land in the same bin and
    Assam looks identical to a state with a sixth of its spend. Equal-width bins on log10 keep the
    outlier alone at the top while still separating the middle of the distribution.
    """
    vals = sorted(v for v in values if v > 0)
    if len(vals) < 2:
        return [0.0] * (n - 1)
    lo, hi = math.log10(vals[0]), math.log10(vals[-1])
    if hi - lo < 1e-9:
        return [vals[-1]] * (n - 1)
    step = (hi - lo) / n
    return [10 ** (lo + step * i) for i in range(1, n)]


def _bin_index(v: float, breaks: list[float]) -> int:
    if v <= 0:
        return 0
    for i, b in enumerate(breaks):
        if v < b:
            return i
    return len(breaks)


def build(con: sqlite3.Connection, fy: str | None = None, theme: str | None = None,
          radius: float = 44.0) -> dict:
    """Return everything a template needs to draw the cartogram, with the numbers to label it."""
    where, args = ["1=1"], []
    if fy:
        where.append("fy=?"); args.append(fy)
    if theme:
        where.append("theme=?"); args.append(theme)
    rows = {r["state_code"]: r for r in con.execute(
        f"""SELECT state_code, ROUND(SUM(spent_cr),2) cr, COUNT(DISTINCT cin) funders, COUNT(*) lines
            FROM csr_projects WHERE {' AND '.join(where)} GROUP BY state_code""", args)}

    values = [rows[s]["cr"] if s in rows else 0.0 for s in LAYOUT]
    breaks = _bins(values)
    total = sum(values)

    tiles = []
    for code, (row, col) in LAYOUT.items():
        cr = rows[code]["cr"] if code in rows else 0.0
        cx = radius * 1.5 * col
        cy = radius * math.sqrt(3) * (row + 0.5 * (col % 2))
        idx = _bin_index(cr, breaks)
        tiles.append({
            "code": code, "name": STATE_NAMES[code], "cr": cr,
            "funders": rows[code]["funders"] if code in rows else 0,
            "lines": rows[code]["lines"] if code in rows else 0,
            "share": (cr / total) if total else 0.0,
            "points": _polygon(cx, cy, radius), "cx": round(cx, 2), "cy": round(cy, 2),
            "fill": RAMP[idx], "bin": idx,
            # keep the label legible on the darkest two bins
            "ink": "#ffffff" if idx >= 3 else "#1b1a17",
            "label": (f"{cr:,.0f}" if cr >= 10 else f"{cr:,.1f}") if cr else "0",
        })
    tiles.sort(key=lambda t: -t["cr"])

    xs = [t["cx"] for t in tiles]; ys = [t["cy"] for t in tiles]
    pad = radius * 1.25
    view = (min(xs) - pad, min(ys) - pad, (max(xs) - min(xs)) + 2 * pad, (max(ys) - min(ys)) + 2 * pad)

    top = tiles[0] if tiles else None
    second = tiles[1] if len(tiles) > 1 else None
    ratio = (top["cr"] / second["cr"]) if top and second and second["cr"] else None
    return {
        "tiles": tiles, "ramp": RAMP, "breaks": breaks, "total_cr": round(total, 2),
        "viewbox": f"{view[0]:.1f} {view[1]:.1f} {view[2]:.1f} {view[3]:.1f}",
        "width": round(view[2], 1), "height": round(view[3], 1),
        "fy": fy, "theme": theme,
        "min_cr": min((t["cr"] for t in tiles), default=0), "max_cr": max((t["cr"] for t in tiles), default=0),
        "lead": {"name": top["name"], "cr": top["cr"], "ratio": round(ratio, 1)} if ratio else None,
        "note": ("One hexagon per state, placed to match their real relative positions. The empty column "
                 "between Sikkim and the rest is the Siliguri corridor. Shading is binned on a log scale "
                 "because one state dominates; the figure inside each tile is the actual amount in "
                 "\u20b9 crore, so nothing depends on colour alone."),
    }
