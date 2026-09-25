"""In-memory project model: boreholes and their interval / point data."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .patterns import Legend

# Columns every table is guaranteed to have after loading.
TABLE_COLUMNS = {
    "boreholes": ["borehole_id", "x", "y", "elevation", "total_depth"],
    "lithology": ["borehole_id", "from", "to", "code", "description"],
    "construction": ["borehole_id", "from", "to", "element", "diameter", "material"],
    "water_levels": ["borehole_id", "date", "depth"],
    "downhole": ["borehole_id", "depth", "parameter", "value", "unit"],
}


def empty_table(name: str) -> pd.DataFrame:
    return pd.DataFrame(columns=TABLE_COLUMNS[name])


@dataclass
class Borehole:
    id: str
    x: float = np.nan
    y: float = np.nan
    elevation: float = np.nan
    total_depth: float = np.nan
    info: dict = field(default_factory=dict)  # any extra collar columns
    lithology: pd.DataFrame = field(default_factory=lambda: empty_table("lithology"))
    construction: pd.DataFrame = field(default_factory=lambda: empty_table("construction"))
    water_levels: pd.DataFrame = field(default_factory=lambda: empty_table("water_levels"))
    downhole: pd.DataFrame = field(default_factory=lambda: empty_table("downhole"))

    @property
    def has_elevation(self) -> bool:
        return pd.notna(self.elevation)

    @property
    def depth(self) -> float:
        """Deepest known depth: total depth, else deepest logged value."""
        cands = [self.total_depth]
        if len(self.lithology):
            cands.append(self.lithology["to"].max())
        if len(self.construction):
            cands.append(self.construction["to"].max())
        if len(self.downhole):
            cands.append(self.downhole["depth"].max())
        cands = [c for c in cands if pd.notna(c)]
        return float(max(cands)) if cands else 0.0


@dataclass
class Project:
    boreholes: pd.DataFrame
    lithology: pd.DataFrame
    construction: pd.DataFrame
    water_levels: pd.DataFrame
    downhole: pd.DataFrame
    legend: Legend = field(default_factory=Legend)
    name: str = "LithoLog project"

    @property
    def ids(self) -> list[str]:
        return list(self.boreholes["borehole_id"])

    def borehole(self, bid: str) -> Borehole:
        rows = self.boreholes[self.boreholes["borehole_id"] == bid]
        if rows.empty:
            raise KeyError(f"Borehole '{bid}' is not in the Boreholes table")
        row = rows.iloc[0].to_dict()
        core = TABLE_COLUMNS["boreholes"]
        info = {k: v for k, v in row.items() if k not in core and _present(v)}

        def sub(df, sort):
            return df[df["borehole_id"] == bid].sort_values(sort).reset_index(drop=True)

        return Borehole(
            id=bid,
            x=row.get("x", np.nan),
            y=row.get("y", np.nan),
            elevation=row.get("elevation", np.nan),
            total_depth=row.get("total_depth", np.nan),
            info=info,
            lithology=sub(self.lithology, "from"),
            construction=sub(self.construction, "from"),
            water_levels=sub(self.water_levels, "date"),
            downhole=sub(self.downhole, ["parameter", "depth"]),
        )

    def __iter__(self):
        return (self.borehole(b) for b in self.ids)


def _present(v) -> bool:
    if v is None:
        return False
    if isinstance(v, float) and np.isnan(v):
        return False
    return str(v).strip() != "" and v is not pd.NaT
