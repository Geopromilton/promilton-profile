"""Data checks that catch the usual borehole-log mistakes before plotting."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .project import Project

TOL = 1e-6


@dataclass
class Issue:
    level: str  # "error" or "warning"
    borehole: str
    message: str

    def __str__(self):
        return f"[{self.level.upper():7}] {self.borehole or '-':>10}: {self.message}"


def validate(project: Project) -> list[Issue]:
    issues: list[Issue] = []
    add = lambda lvl, bh, msg: issues.append(Issue(lvl, bh, msg))  # noqa: E731

    ids = project.boreholes["borehole_id"]
    for bid in ids[ids.duplicated()].unique():
        add("error", bid, "Borehole ID appears more than once in the Boreholes sheet")

    for bh in project:
        if pd.isna(bh.x) or pd.isna(bh.y):
            add("warning", bh.id, "No X/Y coordinates (needed for sections and maps)")
        if pd.isna(bh.total_depth):
            add("warning", bh.id, "No total depth given; using the deepest logged depth")
        td = bh.total_depth

        lith = bh.lithology
        if lith.empty:
            add("warning", bh.id, "No lithology intervals")
        prev_to = 0.0
        for _, r in lith.iterrows():
            f, t = r["from"], r["to"]
            where = f"lithology {_fmt(f)}-{_fmt(t)} m"
            if pd.isna(f) or pd.isna(t):
                add("error", bh.id, f"{where}: From/To is missing or not a number")
                continue
            if f < 0:
                add("error", bh.id, f"{where}: negative depth")
            if t <= f:
                add("error", bh.id, f"{where}: To must be deeper than From")
            if f < prev_to - TOL:
                add("error", bh.id, f"{where}: overlaps the interval above (which ends at {_fmt(prev_to)} m)")
            elif f > prev_to + TOL:
                add("warning", bh.id, f"Gap in lithology between {_fmt(prev_to)} and {_fmt(f)} m")
            if not r["code"]:
                add("error", bh.id, f"{where}: lithology code is empty")
            elif r["code"] not in project.legend:
                add("warning", bh.id, f"{where}: code '{r['code']}' is not in the legend (drawn grey)")
            prev_to = max(prev_to, t)
        if len(lith) and pd.notna(td):
            if prev_to > td + TOL:
                add("warning", bh.id, f"Lithology goes to {_fmt(prev_to)} m, deeper than total depth {_fmt(td)} m")
            elif prev_to < td - TOL:
                add("warning", bh.id, f"Lithology ends at {_fmt(prev_to)} m but total depth is {_fmt(td)} m")

        for _, r in bh.construction.iterrows():
            f, t = r["from"], r["to"]
            if pd.isna(f) or pd.isna(t) or t <= f:
                add("error", bh.id, f"construction '{r['element']}' has invalid From/To ({_fmt(f)}-{_fmt(t)})")
            elif pd.notna(td) and t > td + TOL:
                add("warning", bh.id, f"construction '{r['element']}' extends below total depth")

        for _, r in bh.water_levels.iterrows():
            if pd.isna(r["depth"]):
                add("error", bh.id, "water level with no depth value")
            elif pd.notna(td) and r["depth"] > td:
                add("warning", bh.id, f"water level {_fmt(r['depth'])} m is below total depth")

        dh = bh.downhole
        if len(dh) and (dh["depth"].isna().any() or dh["value"].isna().any()):
            add("warning", bh.id, "some downhole rows have missing depth/value and are skipped")

    return issues


def _fmt(v) -> str:
    return "?" if pd.isna(v) else f"{v:g}"
