"""Groundwater recharge by the water-table fluctuation (WTF) method, as in the GEC-2015 methodology
(Ground Water Resource Estimation Committee, Government of India), with the rainfall-infiltration-
factor (RIF) method alongside for comparison.

WTF, for one season between a pre- and a post-season water-level reading:

    storage change   ΔS = Σ (volume of each unit between the two water tables × its specific yield)
    total recharge   R  = ΔS + gross draft during the season (+ natural discharge, if known)
    rain recharge    Rr = R − recharge from other sources (canals, tanks, irrigation return flow …)
    as a share of rainfall:  Rr / (rainfall × area)

Everything the method needs that is not in the borehole and water-level data — rainfall, draft,
other sources and the specific yield of each unit — is an input the user supplies.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class RechargeResult:
    table: pd.DataFrame        # per unit: volume between water tables, Sy, storage change
    area_km2: float
    mean_rise_m: float
    storage_change_mcm: float
    draft_mcm: float
    other_mcm: float
    rainfall_mm: float | None
    rif: float | None

    @property
    def recharge_mcm(self):
        return self.storage_change_mcm + self.draft_mcm

    @property
    def rain_recharge_mcm(self):
        return self.recharge_mcm - self.other_mcm

    @property
    def rainfall_mcm(self):
        return None if self.rainfall_mm is None else self.rainfall_mm / 1000 * self.area_km2

    @property
    def recharge_pct_of_rain(self):
        rf = self.rainfall_mcm
        return None if not rf else 100 * self.rain_recharge_mcm / rf

    @property
    def rif_recharge_mcm(self):
        rf = self.rainfall_mcm
        return None if (rf is None or self.rif is None) else self.rif * rf

    def summary(self) -> list[str]:
        out = [f"Area {self.area_km2:,.1f} km², mean water-level rise {self.mean_rise_m:+.2f} m",
               f"Storage change ΔS = {self.storage_change_mcm:,.2f} MCM",
               f"Gross draft during the season = {self.draft_mcm:,.2f} MCM",
               f"Total recharge R = ΔS + draft = {self.recharge_mcm:,.2f} MCM",
               f"Recharge from other sources = {self.other_mcm:,.2f} MCM",
               f"Recharge from rainfall = {self.rain_recharge_mcm:,.2f} MCM"
               + (f"  ({self.rain_recharge_mcm / self.area_km2 * 1000:,.0f} mm)" if self.area_km2 else "")]
        if self.rainfall_mm is not None:
            out.append(f"Rainfall {self.rainfall_mm:,.0f} mm = {self.rainfall_mcm:,.1f} MCM → recharge "
                       f"{self.recharge_pct_of_rain:.1f} % of rainfall (WTF)")
        if self.rif_recharge_mcm is not None:
            out.append(f"RIF method (factor {self.rif:g}): {self.rif_recharge_mcm:,.2f} MCM  "
                       f"(WTF / RIF = {self.rain_recharge_mcm / self.rif_recharge_mcm:.2f})")
        return out


def wtf_recharge(model, wells, pre, post, sy: dict, draft_mcm: float = 0.0, other_mcm: float = 0.0,
                 rainfall_mm: float | None = None, rif: float | None = None, method="idw",
                 surface: str = "depth") -> RechargeResult:
    """Water-table fluctuation recharge between readings ``pre`` and ``post``.

    ``sy``: specific yield per unit code; units without one are counted with Sy = 0 and listed.
    """
    from .aquifer import saturated_volumes, water_table

    w0 = water_table(model, wells, pre, method, surface)
    w1 = water_table(model, wells, post, method, surface)
    v0 = saturated_volumes(model, w0, {}).set_index("code")["saturated_mcm"]
    v1 = saturated_volumes(model, w1, {}).set_index("code")["saturated_mcm"]
    dv = (v1 - v0).rename("volume_between_mcm")
    t = dv.reset_index()
    t["specific_yield"] = [sy.get(c, np.nan) for c in t["code"]]
    t["storage_change_mcm"] = t["volume_between_mcm"] * t["specific_yield"].fillna(0)
    rise = w1.grid.z - w0.grid.z
    valid = w1.grid.valid & np.isfinite(rise)
    area = float(valid.sum()) * w1.grid.cell ** 2 / 1e6
    return RechargeResult(t, area, float(np.nanmean(np.where(valid, rise, np.nan))),
                          float(t["storage_change_mcm"].sum()), float(draft_mcm), float(other_mcm),
                          rainfall_mm, rif)
