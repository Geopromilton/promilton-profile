"""Hydrochemistry: ionic balance, water type, irrigation indices and diagrams.

Input: one row per sample with major ions in mg/L (columns such as Ca, Mg, Na,
K, HCO3, CO3, Cl, SO4, NO3), plus optional EC (µS/cm), TDS (mg/L), pH and a
Group column. Columns whose header says "meq" are taken as meq/L.

Diagrams: Piper, Durov, Stiff, USSL (Richards 1954) salinity/sodium hazard,
Wilcox (1955) classes, Gibbs. Indices: SAR, %Na, RSC, Kelly's ratio,
permeability index, magnesium hazard.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from .io import normalize

# ion: (molar mass g/mol, charge)
IONS = {"ca": (40.078, 2), "mg": (24.305, 2), "na": (22.990, 1), "k": (39.098, 1),
        "hco3": (61.017, 1), "co3": (60.009, 2), "cl": (35.453, 1), "so4": (96.06, 2), "no3": (62.004, 1),
        "f": (18.998, 1)}
CATIONS = ["ca", "mg", "na", "k"]
ANIONS = ["hco3", "co3", "cl", "so4", "no3", "f"]
ALIASES = {
    "sample": ["sample", "sample_id", "id", "well", "well_id", "station", "location", "name", "borehole_id",
               "village", "sl_no"],
    "group": ["group", "type", "aquifer", "season", "category", "zone", "class"],
    "ca": ["ca", "calcium", "ca2", "ca_2"], "mg": ["mg", "magnesium", "mg2", "mg_2"],
    "na": ["na", "sodium"], "k": ["k", "potassium"],
    "hco3": ["hco3", "bicarbonate", "hco3_", "alkalinity_hco3"], "co3": ["co3", "carbonate", "co3_2"],
    "cl": ["cl", "chloride"], "so4": ["so4", "sulphate", "sulfate", "so4_2"], "no3": ["no3", "nitrate"],
    "f": ["f", "fluoride"],
    "ec": ["ec", "conductivity", "electrical_conductivity", "ec_us_cm", "spc"],
    "tds": ["tds", "total_dissolved_solids"], "ph": ["ph"],
}
NAVY = "#1F3A5F"
GROUP_COLORS = ["#1F77B4", "#D62728", "#2CA02C", "#FF7F0E", "#9467BD", "#8C564B", "#E377C2", "#17BECF"]


def _base(name: str) -> str:
    n = normalize(name)
    for suffix in ("_mg_l", "_mgl", "_mg", "_meq_l", "_meq", "_ppm"):
        if n.endswith(suffix):
            return n[: -len(suffix)]
    return n


def load_chemistry(path_or_df) -> pd.DataFrame:
    """Standardised table: sample, group, ions (mg/L), ec, tds, ph."""
    if isinstance(path_or_df, pd.DataFrame):
        raw = path_or_df.copy()
    else:
        p = Path(path_or_df)
        raw = pd.read_excel(p) if p.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(p, sep=None,
                                                                                          engine="python")
    raw = raw.dropna(how="all")
    out = pd.DataFrame(index=raw.index)
    for key, alts in ALIASES.items():
        col = next((c for c in raw.columns if _base(c) in alts), None)
        if col is None:
            continue
        if key in ("sample", "group"):
            out[key] = raw[col].astype(str).str.strip()
        else:
            v = pd.to_numeric(raw[col].astype(str).str.replace("<", "", regex=False).str.replace(",", ""),
                              errors="coerce")
            if key in IONS and "meq" in normalize(col):
                mass, z = IONS[key]
                v = v * mass / z  # meq/L → mg/L
            out[key] = v
    if "sample" not in out:
        out["sample"] = [f"S{i + 1}" for i in range(len(out))]
    if "group" not in out:
        out["group"] = "All samples"
    missing = [i for i in ("ca", "mg", "na", "hco3", "cl", "so4") if i not in out]
    if missing:
        raise ValueError(f"Missing major-ion columns: {', '.join(missing)}")
    for i in IONS:
        if i not in out:
            out[i] = 0.0
    return out.reset_index(drop=True)


def meq(df: pd.DataFrame) -> pd.DataFrame:
    m = pd.DataFrame(index=df.index)
    for ion, (mass, z) in IONS.items():
        m[ion] = df[ion].fillna(0) * z / mass
    return m


def analyse(df: pd.DataFrame) -> pd.DataFrame:
    """Ionic balance, water type and irrigation indices for every sample."""
    m = meq(df)
    cat = m[CATIONS].sum(1)
    an = m[ANIONS].sum(1)
    res = df[["sample", "group"]].copy()
    for ion in IONS:
        res[f"{ion}_meq"] = m[ion].round(3)
    res["sum_cations_meq"] = cat.round(3)
    res["sum_anions_meq"] = an.round(3)
    res["ionic_balance_pct"] = (100 * (cat - an) / (cat + an)).round(2)
    res["balance_ok_5pct"] = res["ionic_balance_pct"].abs() <= 5
    ca, mg, na, k = m["ca"], m["mg"], m["na"], m["k"]
    hco3 = m["hco3"] + m["co3"]
    res["SAR"] = (na / np.sqrt((ca + mg) / 2)).round(2)
    res["Na_pct"] = (100 * (na + k) / (ca + mg + na + k)).round(1)
    res["RSC_meq"] = (hco3 - (ca + mg)).round(2)
    res["Kelly_ratio"] = (na / (ca + mg)).round(2)
    res["PI_pct"] = (100 * (na + np.sqrt(m["hco3"])) / (ca + mg + na)).round(1)
    res["MH_pct"] = (100 * mg / (ca + mg)).round(1)
    res["water_type"] = [water_type(r) for _, r in m.iterrows()]
    if "ec" in df:
        res["EC_uS_cm"] = df["ec"]
        res["USSL_class"] = [ussl_class(e, s) for e, s in zip(df["ec"], res["SAR"])]
        res["Wilcox_class"] = [wilcox_class(e, p) for e, p in zip(df["ec"], res["Na_pct"])]
    if "tds" in df:
        res["TDS_mg_L"] = df["tds"]
    return res


def water_type(r) -> str:
    cats = {"Ca": r["ca"], "Mg": r["mg"], "Na": r["na"] + r["k"]}
    ans = {"HCO3": r["hco3"] + r["co3"], "Cl": r["cl"], "SO4": r["so4"]}
    return f"{max(cats, key=cats.get)}-{max(ans, key=ans.get)}"


def ussl_class(ec, sar) -> str:
    if pd.isna(ec) or pd.isna(sar):
        return ""
    c = 1 + sum(ec > b for b in (250, 750, 2250))
    le = math.log10(max(ec, 1))
    lines = [18.87 - 4.44 * le, 31.31 - 6.66 * le, 43.75 - 8.87 * le]
    s = 1 + sum(sar > b for b in lines)
    return f"C{c}S{s}"


WILCOX = ["Excellent", "Good", "Permissible", "Doubtful", "Unsuitable"]


def wilcox_class(ec, na_pct) -> str:
    """Worse of the EC and %Na classes of Wilcox (1955)."""
    if pd.isna(ec) or pd.isna(na_pct):
        return ""
    ce = sum(ec > b for b in (250, 750, 2000, 3000))
    cn = sum(na_pct > b for b in (20, 40, 60, 80))
    return WILCOX[max(ce, cn)]


# ---------------------------------------------------------------------------
# Diagrams (matplotlib)

H = math.sqrt(3) / 2


def _groups(df):
    return list(dict.fromkeys(df["group"]))


def _style(ax):
    ax.set_aspect("equal")
    ax.set_axis_off()


def _tri_grid(ax, origin, flip=False, step=0.2):
    ox, oy = origin
    pts = [(ox, oy), (ox + 1, oy), (ox + 0.5, oy + H)]
    ax.plot(*zip(*(pts + pts[:1])), color="k", lw=0.9)
    for f in np.arange(step, 1, step):
        # lines parallel to each side
        ax.plot([ox + f / 2, ox + 1 - f / 2], [oy + f * H, oy + f * H], color="#BBBBBB", lw=0.4)
        ax.plot([ox + f, ox + 0.5 + f / 2], [oy, oy + (1 - f) * H], color="#BBBBBB", lw=0.4)
        ax.plot([ox + f, ox + f / 2], [oy, oy + f * H], color="#BBBBBB", lw=0.4)


def piper(df, ax=None, title="Piper diagram"):
    import matplotlib.pyplot as plt

    m = meq(df)
    cat = m[CATIONS].sum(1)
    an = m[ANIONS].sum(1)
    ca, mg, nak = m["ca"] / cat, m["mg"] / cat, (m["na"] + m["k"]) / cat
    hc, cl, so4 = (m["hco3"] + m["co3"]) / an, (m["cl"] + m["no3"] + m["f"]) / an, m["so4"] / an
    gap = 0.2
    off = 1 + gap
    xc, yc = nak + 0.5 * mg, H * mg
    xa, ya = off + cl + 0.5 * so4, H * so4

    def diamond_pt(xc, yc, xa, ya):
        # line from cation point along (0.5, H); from anion point along (-0.5, H)
        t = ((xa - xc) + 0.5 * (ya - yc) / H) / 1.0
        return xc + 0.5 * t, yc + H * t

    if ax is None:
        fig, ax = plt.subplots(figsize=(8.5, 8))
    _tri_grid(ax, (0, 0))
    _tri_grid(ax, (off, 0))
    corners = [diamond_pt(*a, *b) for a, b in [((0, 0), (off + 1, 0)), ((1, 0), (off + 1, 0)),
                                             ((1, 0), (off, 0)), ((0, 0), (off, 0))]]
    ax.plot(*zip(*(corners + corners[:1])), color="k", lw=0.9)
    # diamond grid
    for f in np.arange(0.2, 1, 0.2):
        a = diamond_pt(f, 0, off + 1, 0)
        b = diamond_pt(f, 0, off, 0)
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#BBBBBB", lw=0.4)
        a = diamond_pt(0, 0, off + f, 0)
        b = diamond_pt(1, 0, off + f, 0)
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#BBBBBB", lw=0.4)
    dx, dy = diamond_pt(xc, yc, xa, ya)
    for gi, g in enumerate(_groups(df)):
        sel = df["group"] == g
        c = GROUP_COLORS[gi % len(GROUP_COLORS)]
        for X, Y in ((xc, yc), (xa, ya), (dx, dy)):
            ax.scatter(X[sel], Y[sel], s=28, color=c, edgecolor="k", lw=0.4, zorder=5,
                       label=g if X is xc else None)
    fs = 8
    ax.text(-0.03, -0.03, "Ca²⁺", ha="right", va="top", fontsize=fs)
    ax.text(0.97, -0.06, "Na⁺+K⁺", ha="center", va="top", fontsize=fs)
    ax.text(0.5, H + 0.03, "Mg²⁺", ha="center", fontsize=fs)
    ax.text(off + 0.03, -0.06, "HCO₃⁻+CO₃²⁻", ha="center", va="top", fontsize=fs)
    ax.text(off + 1.03, -0.03, "Cl⁻", ha="left", va="top", fontsize=fs)
    ax.text(off + 0.5, H + 0.03, "SO₄²⁻", ha="center", fontsize=fs)
    top = max(c[1] for c in corners)
    ax.text(0.5, -0.16, "Cations (% meq/L)", ha="center", fontsize=8, color="#555555")
    ax.text(off + 0.5, -0.16, "Anions (% meq/L)", ha="center", fontsize=8, color="#555555")
    ax.set_title(title, fontsize=12, fontweight="bold", color=NAVY)
    if len(_groups(df)) > 1 or _groups(df)[0] != "All samples":
        ax.legend(loc="upper left", fontsize=8, frameon=False)
    ax.set_xlim(-0.2, off + 1.2)
    ax.set_ylim(-0.22, top + 0.05)
    _style(ax)
    return ax


def durov(df, ax=None, title="Durov diagram"):
    """Cation triangle (left), anion triangle (top); sample plotted in the square
    at the intersection of the perpendicular projections of both points."""
    import matplotlib.pyplot as plt

    m = meq(df)
    cat = m[CATIONS].sum(1)
    an = m[ANIONS].sum(1)
    mg, nak = m["mg"] / cat, (m["na"] + m["k"]) / cat
    cl, so4 = (m["cl"] + m["no3"] + m["f"]) / an, m["so4"] / an
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 8))
    # square
    ax.plot([0, 1, 1, 0, 0], [0, 0, 1, 1, 0], color="k", lw=0.9)
    for f in np.arange(0.2, 1, 0.2):
        ax.plot([f, f], [0, 1], color="#BBBBBB", lw=0.4)
        ax.plot([0, 1], [f, f], color="#BBBBBB", lw=0.4)
    # anion triangle on top: HCO3 at (0,1), Cl at (1,1), SO4 at apex
    ax.plot([0, 1, 0.5, 0], [1, 1, 1 + H, 1], color="k", lw=0.9)
    # cation triangle on left: Ca at (0,0), Na+K at (0,1), Mg at apex
    ax.plot([0, 0, -H, 0], [0, 1, 0.5, 0], color="k", lw=0.9)
    xa, ya = cl + 0.5 * so4, 1 + H * so4
    yc, xc = nak + 0.5 * mg, -H * mg
    for gi, g in enumerate(_groups(df)):
        sel = df["group"] == g
        c = GROUP_COLORS[gi % len(GROUP_COLORS)]
        ax.scatter(xa[sel], ya[sel], s=24, color=c, edgecolor="k", lw=0.4, zorder=5, label=g)
        ax.scatter(xc[sel], yc[sel], s=24, color=c, edgecolor="k", lw=0.4, zorder=5)
        ax.scatter(xa[sel], yc[sel], s=34, color=c, edgecolor="k", lw=0.5, zorder=6)
    fs = 8
    ax.text(0, 1.03, "HCO₃⁻", ha="right", fontsize=fs)
    ax.text(1.0, 1.03, "Cl⁻", ha="left", fontsize=fs)
    ax.text(0.5, 1 + H + 0.03, "SO₄²⁻", ha="center", fontsize=fs)
    ax.text(0.02, -0.05, "Ca²⁺", ha="left", fontsize=fs)
    ax.text(0.02, 1.0, "Na⁺+K⁺", ha="left", va="top", fontsize=fs)
    ax.text(-H - 0.03, 0.5, "Mg²⁺", ha="right", va="center", fontsize=fs)
    ax.set_title(title, fontsize=12, fontweight="bold", color=NAVY)
    if len(_groups(df)) > 1 or _groups(df)[0] != "All samples":
        ax.legend(loc="upper right", fontsize=8, frameon=False)
    ax.set_xlim(-H - 0.2, 1.15)
    ax.set_ylim(-0.12, 1 + H + 0.12)
    _style(ax)
    return ax


def stiff(df, path_or_fig=None, cols=4, title="Stiff diagrams"):
    import matplotlib.pyplot as plt

    m = meq(df)
    n = len(df)
    rows = max(1, math.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.2, rows * 2.2 + 0.8), squeeze=False)
    xmax = float(max((m["na"] + m["k"]).max(), m["ca"].max(), m["mg"].max(), m["cl"].max(),
                     (m["hco3"] + m["co3"]).max(), m["so4"].max()) * 1.1) or 1
    for i, ax in enumerate(axes.ravel()):
        if i >= n:
            ax.set_axis_off()
            continue
        r = m.iloc[i]
        xs = [-(r["na"] + r["k"]), -r["ca"], -r["mg"], r["so4"], r["hco3"] + r["co3"], r["cl"]]
        ys = [2, 1, 0, 0, 1, 2]
        ax.fill(xs, ys, color="#7FB3D5", edgecolor=NAVY, lw=1)
        ax.axvline(0, color="k", lw=0.6)
        for y in (0, 1, 2):
            ax.axhline(y, color="#DDDDDD", lw=0.4, zorder=0)
        ax.set_xlim(-xmax, xmax)
        ax.set_ylim(-0.4, 2.4)
        ax.set_yticks([0, 1, 2])
        ax.set_yticklabels(["Mg", "Ca", "Na+K"], fontsize=7)
        ax2 = ax.twinx()
        ax2.set_ylim(-0.4, 2.4)
        ax2.set_yticks([0, 1, 2])
        ax2.set_yticklabels(["SO₄", "HCO₃+CO₃", "Cl"], fontsize=7)
        ax.tick_params(axis="x", labelsize=6)
        ax.set_title(str(df["sample"].iloc[i]), fontsize=8, fontweight="bold")
    fig.suptitle(f"{title}  (meq/L; cations left, anions right)", fontsize=12, fontweight="bold", color=NAVY)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def ussl(df, res, ax=None, title="USSL diagram (salinity and sodium hazard)"):
    import matplotlib.pyplot as plt

    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 7))
    ec = np.linspace(100, 10000, 400)
    le = np.log10(ec)
    for a, b in ((18.87, 4.44), (31.31, 6.66), (43.75, 8.87)):
        ax.plot(ec, a - b * le, color="k", lw=0.8)
    for x in (250, 750, 2250):
        ax.axvline(x, color="k", lw=0.8)
    for gi, g in enumerate(_groups(df)):
        sel = (df["group"] == g).to_numpy()
        ax.scatter(df["ec"][sel], res["SAR"][sel], s=30, color=GROUP_COLORS[gi % len(GROUP_COLORS)],
                   edgecolor="k", lw=0.4, zorder=5, label=g)
    ax.set_xscale("log")
    ax.set_xlim(100, 10000)
    ax.set_ylim(0, 32)
    ax.set_xlabel("Salinity hazard: EC (µS/cm at 25 °C)")
    ax.set_ylabel("Sodium hazard: SAR")
    for x, lab in ((160, "C1 Low"), (430, "C2 Medium"), (1300, "C3 High"), (4700, "C4 Very high")):
        ax.text(x, 31, lab, ha="center", va="top", fontsize=7, color="#555555")
    for y, lab in ((3, "S1 Low"), (11, "S2 Medium"), (19, "S3 High"), (27, "S4 Very high")):
        ax.text(110, y, lab, fontsize=7, color="#555555")
    ax.set_title(title, fontsize=12, fontweight="bold", color=NAVY)
    ax.text(0.99, 0.01, "Class limits after Richards (1954)", transform=ax.transAxes, ha="right",
            fontsize=6, color="#777777")
    if len(_groups(df)) > 1 or _groups(df)[0] != "All samples":
        ax.legend(fontsize=8, frameon=False, loc="upper right", bbox_to_anchor=(1, 0.93))
    return ax


def wilcox(df, res, ax=None, title="Wilcox classification (EC vs %Na)"):
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 6.5))
    ex = np.linspace(0, 4000, 401)
    npct = np.linspace(0, 100, 201)
    E, N = np.meshgrid(ex, npct)
    cls = np.maximum(np.searchsorted([250, 750, 2000, 3000], E, side="left"),
                     np.searchsorted([20, 40, 60, 80], N, side="left"))
    cmap = ListedColormap(["#CFE8CF", "#E6F2C2", "#FFF2B3", "#FFD6A5", "#F4B6B6"])
    ax.pcolormesh(E, N, cls, cmap=cmap, vmin=-0.5, vmax=4.5, shading="auto", zorder=0)
    for k, name in enumerate(WILCOX):
        ax.text([120, 500, 1350, 2500, 3500][k], [10, 30, 50, 70, 92][k], name, fontsize=8, ha="center",
                color="#444444")
    for gi, g in enumerate(_groups(df)):
        sel = (df["group"] == g).to_numpy()
        ax.scatter(df["ec"][sel], res["Na_pct"][sel], s=30, color=GROUP_COLORS[gi % len(GROUP_COLORS)],
                   edgecolor="k", lw=0.4, zorder=5, label=g)
    ax.set_xlim(0, 4000)
    ax.set_ylim(0, 100)
    ax.set_xlabel("EC (µS/cm)")
    ax.set_ylabel("Sodium (%)")
    ax.set_title(title, fontsize=12, fontweight="bold", color=NAVY)
    ax.text(0.99, 0.01, "Class limits from the Wilcox (1955) table; class = worse of EC and %Na",
            transform=ax.transAxes, ha="right", fontsize=6, color="#555555")
    if len(_groups(df)) > 1 or _groups(df)[0] != "All samples":
        ax.legend(fontsize=8, frameon=False)
    return ax


def gibbs(df, fig=None, title="Gibbs diagrams (indicative fields)"):
    import matplotlib.pyplot as plt

    m = meq(df)
    tds = df["tds"] if "tds" in df and df["tds"].notna().any() else df.get("ec", pd.Series(np.nan)) * 0.64
    r1 = df["na"] / (df["na"] + df["ca"])  # mg/L ratios, as in Gibbs (1970)
    r2 = df["cl"] / (df["cl"] + df["hco3"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5), sharey=True)
    for ax, r, lab in ((axes[0], r1, "Na⁺ / (Na⁺ + Ca²⁺)"), (axes[1], r2, "Cl⁻ / (Cl⁻ + HCO₃⁻)")):
        for gi, g in enumerate(_groups(df)):
            sel = (df["group"] == g).to_numpy()
            ax.scatter(r[sel], tds[sel], s=30, color=GROUP_COLORS[gi % len(GROUP_COLORS)], edgecolor="k",
                       lw=0.4, zorder=5, label=g)
        ax.set_yscale("log")
        ax.set_xlim(0, 1)
        ax.set_ylim(1, 100000)
        ax.set_xlabel(lab)
        ax.text(0.85, 15, "Precipitation\ndominance", ha="center", fontsize=8, color="#555555")
        ax.text(0.3, 250, "Rock\ndominance", ha="center", fontsize=8, color="#555555")
        ax.text(0.85, 12000, "Evaporation\ndominance", ha="center", fontsize=8, color="#555555")
        ax.grid(True, which="both", color="#EEEEEE", lw=0.4)
    axes[0].set_ylabel("TDS (mg/L)")
    fig.suptitle(title, fontsize=12, fontweight="bold", color=NAVY)
    fig.tight_layout()
    del m
    return fig


def report(df, out_dir, title: str = "") -> list[Path]:
    """All diagrams + a results table; returns the files written."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    res = analyse(df)
    files = []
    figs = []
    fig, ax = plt.subplots(figsize=(8.5, 8))
    piper(df, ax, f"Piper diagram{(' – ' + title) if title else ''}")
    figs.append(("piper", fig))
    fig, ax = plt.subplots(figsize=(8, 8))
    durov(df, ax, f"Durov diagram{(' – ' + title) if title else ''}")
    figs.append(("durov", fig))
    figs.append(("stiff", stiff(df)))
    if "ec" in df and df["ec"].notna().any():
        fig, ax = plt.subplots(figsize=(8, 7))
        ussl(df, res, ax)
        figs.append(("ussl", fig))
        fig, ax = plt.subplots(figsize=(8, 6.5))
        wilcox(df, res, ax)
        figs.append(("wilcox", fig))
    if ("tds" in df and df["tds"].notna().any()) or ("ec" in df and df["ec"].notna().any()):
        figs.append(("gibbs", gibbs(df)))
    with PdfPages(out / "hydrochemistry.pdf") as pdf:
        for name, f in figs:
            f.savefig(out / f"{name}.png", dpi=200)
            pdf.savefig(f)
            files.append(out / f"{name}.png")
            plt.close(f)
    files.append(out / "hydrochemistry.pdf")
    res.to_csv(out / "hydrochemistry_results.csv", index=False)
    files.append(out / "hydrochemistry_results.csv")
    return files
