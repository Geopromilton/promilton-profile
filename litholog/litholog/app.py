"""LithoLog browser app (Streamlit).

Run with ``litholog app`` (or ``streamlit run litholog/app.py``). Everything the
command line does is available here with point-and-click: upload a workbook
or GMS file (plus an optional legend and study-area shapefile), then view and
download strip logs, sections, fence diagrams, maps and the 3D model.
"""

from __future__ import annotations

import hashlib
import io
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

import litholog
from litholog.io import load_project, write_template

HERE = Path(__file__).resolve().parent
DEMO = HERE / "data" / "sample_project.xlsx"
TMP = Path(tempfile.gettempdir()) / "litholog_app"
TMP.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="LithoLog", page_icon="🪨", layout="wide")


# ---------------------------------------------------------------------------
# Inputs


def _save(upload, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / upload.name
    p.write_bytes(upload.getvalue())
    return p


def _digest(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
    return h.hexdigest()[:12]


@st.cache_resource(show_spinner="Reading data…")
def _project(key: str, data_path: str, legend_path: str | None):
    return load_project(data_path, legend=legend_path)


@st.cache_resource(show_spinner="Reading boundary…")
def _boundary(key: str, shp: str, crs: str | None, near):
    from litholog.boundary import load_boundary

    return load_boundary(shp, crs=crs or None, near=near)


def sidebar():
    st.sidebar.title("🪨 LithoLog")
    st.sidebar.caption(f"Open-source borehole logging · v{litholog.__version__}")
    source = st.sidebar.radio("Data", ["Upload my data", "Demo data (synthetic)"], index=0)
    data_up = legend_up = None
    bnd_ups = []
    if source == "Upload my data":
        data_up = st.sidebar.file_uploader(
            "Borehole data", type=["xlsx", "xls", "txt", "dat", "tsv", "csv"],
            help="LithoLog Excel workbook, or a GMS borehole file (Name, X, Y, Z, Material).")
        legend_up = st.sidebar.file_uploader(
            "Legend (optional)", type=["csv", "xlsx"],
            help="Code, Name, Color, Pattern — names and colours for your lithology codes.")
        bnd_ups = st.sidebar.file_uploader(
            "Study-area boundary (optional)", type=["zip", "shp", "shx", "dbf", "prj", "cpg"],
            accept_multiple_files=True,
            help="A zipped shapefile, or select the .shp, .shx, .dbf and .prj files together.")
    crs = st.sidebar.text_input("Borehole coordinate system (optional)", placeholder="e.g. EPSG:32643",
                                help="Only needed if the boundary is in another system and cannot be "
                                     "matched automatically.")
    title = st.sidebar.text_input("Project name", value="")
    with st.sidebar.expander("New project? Get the input template"):
        buf = io.BytesIO()
        tpath = TMP / "litholog_template.xlsx"
        write_template(tpath)
        buf.write(tpath.read_bytes())
        st.download_button("Download Excel template", buf.getvalue(), "litholog_template.xlsx")

    if source.startswith("Demo"):
        data_path, legend_path, key = DEMO, None, "demo"
    elif data_up is None:
        return None
    else:
        key = _digest(data_up.getvalue(), legend_up.getvalue() if legend_up else b"")
        folder = TMP / key
        data_path = _save(data_up, folder)
        legend_path = _save(legend_up, folder) if legend_up else None
    project = _project(key, str(data_path), str(legend_path) if legend_path else None)
    if title:
        project.name = title

    boundary = None
    if bnd_ups:
        bkey = _digest(*[u.getvalue() for u in bnd_ups], crs)
        bfolder = TMP / f"b_{bkey}"
        for u in bnd_ups:
            p = _save(u, bfolder)
            if p.suffix.lower() == ".zip":
                with zipfile.ZipFile(p) as z:
                    z.extractall(bfolder)
        shps = sorted(bfolder.rglob("*.shp"))
        if not shps:
            st.sidebar.error("No .shp file found in the boundary upload.")
        else:
            b = project.boreholes.dropna(subset=["x", "y"])
            near = (b["x"].min(), b["x"].max(), b["y"].min(), b["y"].max()) if len(b) else None
            try:
                boundary = _boundary(bkey, str(shps[0]), crs, near)
                if boundary.crs_note:
                    note = boundary.crs_note
                    st.sidebar.info(f"Study area: {note[0].upper()}{note[1:]}.")
            except Exception as e:  # noqa: BLE001 - show the reason to the user
                st.sidebar.error(str(e))
    return project, boundary, key


# ---------------------------------------------------------------------------
# Helpers


def _download(label, path: Path, mime=None, key=None):
    st.download_button(label, Path(path).read_bytes(), Path(path).name, mime=mime, key=key)


def _codes(project):
    used = list(dict.fromkeys(c for c in project.lithology["code"] if c))
    return used, {c: f"{project.legend.get(c).name} ({c})" for c in used}


def _out(key, *parts) -> Path:
    p = TMP / key / "out" / "_".join(str(x) for x in parts if x not in (None, ""))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Tabs


def tab_overview(project, boundary):
    import plotly.graph_objects as go

    from litholog.validate import validate

    b = project.boreholes
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Boreholes", len(b))
    c2.metric("Lithology intervals", len(project.lithology))
    c3.metric("Lithology codes", project.lithology["code"].nunique())
    c4.metric("Deepest hole (m)", f"{max((bh.depth for bh in project), default=0):g}")
    left, right = st.columns([3, 2])
    with left:
        fig = go.Figure()
        if boundary is not None:
            for r in boundary.rings:
                fig.add_trace(go.Scatter(x=list(r[:, 0]) + [r[0, 0]], y=list(r[:, 1]) + [r[0, 1]],
                                         mode="lines", line=dict(color="#8B0000", width=2),
                                         name="Study area", hoverinfo="skip"))
        bb = b.dropna(subset=["x", "y"])
        fig.add_trace(go.Scatter(x=bb["x"], y=bb["y"], mode="markers+text", text=bb["borehole_id"],
                                 textposition="top center", textfont=dict(size=9),
                                 marker=dict(size=8, color="#1F3A5F"), name="Boreholes"))
        fig.update_layout(height=520, margin=dict(l=10, r=10, t=30, b=10), title="Borehole locations",
                          xaxis=dict(title="X / Easting", tickformat="d"),
                          yaxis=dict(title="Y / Northing", tickformat="d", scaleanchor="x"),
                          showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with right:
        issues = validate(project)
        errors = [i for i in issues if i.level == "error"]
        st.subheader("Data check")
        if not issues:
            st.success("No problems found.")
        else:
            (st.error if errors else st.warning)(
                f"{len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
            st.dataframe(pd.DataFrame([{"Level": i.level, "Borehole": i.borehole, "Issue": i.message}
                                       for i in issues]), width="stretch", height=260)
        if boundary is not None:
            st.info(f"Study area: {boundary.area / 1e6:,.1f} km²")
        st.subheader("Legend")
        used, names = _codes(project)
        st.dataframe(pd.DataFrame([{"Code": c, "Name": project.legend.get(c).name,
                                    "Colour": project.legend.get(c).color,
                                    "Pattern": project.legend.get(c).pattern} for c in used]),
                     width="stretch", hide_index=True)
    st.subheader("Boreholes")
    st.dataframe(b, width="stretch", height=240)


def tab_striplogs(project, key):
    from litholog.striplog import Style, save_striplog

    c1, c2 = st.columns([1, 3])
    with c1:
        bid = st.selectbox("Borehole", project.ids)
        mpp = st.number_input("Metres per page (0 = whole hole on one page)", 0.0, 1000.0, 0.0, 10.0)
        style = Style(project_name=project.name)
        png = save_striplog(project.borehole(bid), project.legend, _out(key, "log", bid, ".png"),
                            style, mpp or None, dpi=110)
        pdf = save_striplog(project.borehole(bid), project.legend, _out(key, "log", bid, ".pdf"),
                            style, mpp or None)[0]
        _download("⬇ Strip log (PDF)", pdf, "application/pdf")
        if st.button("Prepare all strip logs (one PDF)"):
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_pdf import PdfPages

            from litholog.striplog import striplog_pages

            allp = _out(key, "all_logs.pdf")
            with st.spinner("Drawing all boreholes…"), PdfPages(allp) as pdfp:
                for b in project.ids:
                    for fig in striplog_pages(project.borehole(b), project.legend, style, mpp or None):
                        pdfp.savefig(fig)
                        plt.close(fig)
            _download("⬇ All strip logs (PDF)", allp, "application/pdf", key="all_logs")
    with c2:
        for p in png:
            st.image(str(p), width="stretch")


def tab_section(project, key, title):
    from litholog.section import along_line, save_section, through_boreholes

    c1, c2 = st.columns([1, 3])
    with c1:
        mode = st.radio("Section line", ["Through boreholes (in order)", "Along a line (X,Y points)"])
        name = st.text_input("Section name", "A-A'")
        if mode.startswith("Through"):
            ids = st.multiselect("Boreholes, in order along the section", project.ids,
                                 default=project.ids[:3] if len(project.ids) >= 3 else project.ids)
        else:
            pts = st.text_area("Vertices, one 'X, Y' per line", "", height=90)
            buf = st.number_input("Include holes within (m)", 0.0, 1e6, 500.0, 100.0)
        ve = st.number_input("Vertical exaggeration (0 = fit page)", 0.0, 10000.0, 0.0, 5.0)
        page = st.selectbox("Page", ["A3", "A4"])
        datum = st.selectbox("Hang holes by", ["elevation", "depth"])
    with c2:
        try:
            if mode.startswith("Through"):
                if len(ids) < 2:
                    st.info("Pick at least two boreholes.")
                    return
                line = through_boreholes(project, ids, name)
            else:
                verts = [tuple(float(v) for v in ln.replace(";", ",").split(",")[:2])
                         for ln in pts.strip().splitlines() if ln.strip()]
                if len(verts) < 2:
                    st.info("Enter at least two X, Y points.")
                    return
                line = along_line(project, verts, buf, name)
            kw = dict(ve=ve or None, page=page, title=title, datum=datum)
            png = save_section(project, line, _out(key, "section", name, ".png"), dpi=110, **kw)
            pdf = save_section(project, line, _out(key, "section", name, ".pdf"), **kw)
            st.image(str(png), width="stretch")
            _download("⬇ Section (PDF)", pdf, "application/pdf")
        except ValueError as e:
            st.error(str(e))


def tab_fence(project, key, title):
    from litholog.fence import network_edges, save_fence

    c1, c2 = st.columns([1, 3])
    with c1:
        net = st.selectbox("Network", ["mst", "delaunay"],
                           format_func=lambda n: {"mst": "Nearest neighbours (no crossings)",
                                                  "delaunay": "Triangulated (denser)"}[n])
        azim = st.slider("View direction (°)", -180, 180, -60, 5)
        elev = st.slider("View height (°)", 5, 90, 28, 1)
        ve = st.number_input("Vertical exaggeration (0 = auto)", 0.0, 10000.0, 0.0, 5.0, key="fve")
    with c2:
        try:
            edges = network_edges(project, None, net)
            kw = dict(ve=ve or None, azim=azim, elev=elev, title=title)
            png = save_fence(project, edges, _out(key, "fence", net, azim, elev, ".png"), dpi=110, **kw)[0]
            pdf = save_fence(project, edges, _out(key, "fence", net, azim, elev, ".pdf"), **kw)[0]
            st.image(str(png), width="stretch")
            _download("⬇ Fence diagram (PDF)", pdf, "application/pdf")
        except ValueError as e:
            st.error(str(e))


ATTRS = {"ground": "Ground elevation", "top": "Top of a unit", "base": "Base of a unit",
         "depth": "Depth to a unit", "thickness": "Thickness of a unit (isopach)",
         "water": "Water-table elevation", "dtw": "Depth to water", "total_depth": "Drilled depth"}


def tab_maps(project, boundary, key, title):
    import numpy as np

    from litholog.grid import grid_attribute, write_ascii_grid
    from litholog.maps import save_map

    c1, c2 = st.columns([1, 3])
    with c1:
        kind = st.selectbox("Map", list(ATTRS), format_func=ATTRS.get)
        attr = kind
        if kind in ("top", "base", "depth", "thickness"):
            used, names = _codes(project)
            code = st.selectbox("Unit", used, format_func=names.get)
            attr = f"{kind}:{code}"
        method = st.selectbox("Gridding", ["idw", "linear", "kriging"],
                              format_func=lambda m: {"idw": "Inverse distance (honours data)",
                                                     "linear": "Linear (TIN)",
                                                     "kriging": "Ordinary kriging"}[m])
        cell = st.number_input("Cell size (m, 0 = auto)", 0.0, 1e5, 0.0, 50.0)
        use_b = st.checkbox("Clip to study-area boundary", value=boundary is not None,
                            disabled=boundary is None)
        page = st.selectbox("Page", ["A3", "A4"], key="mpage")
    with c2:
        try:
            g, vals = grid_attribute(project, attr, method, cell or None,
                                     boundary=boundary if use_b else None)
            kw = dict(legend=project.legend, method=method, title=title, page=page, all_xy=project.boreholes)
            tag = (attr.replace(":", "_"), method, cell, use_b)
            png = save_map(g, vals, attr, _out(key, "map", *tag, ".png"), dpi=110, **kw)
            pdf = save_map(g, vals, attr, _out(key, "map", *tag, ".pdf"), **kw)
            st.image(str(png), width="stretch")
            d1, d2, d3 = st.columns(3)
            with d1:
                _download("⬇ Map (PDF)", pdf, "application/pdf")
            with d2:
                _download("⬇ Grid (.asc for QGIS/ArcGIS)", write_ascii_grid(g, _out(key, "map", *tag, ".asc")))
            with d3:
                st.download_button("⬇ Borehole values (CSV)", vals.to_csv(index=False).encode(),
                                   f"{attr.replace(':', '_')}_values.csv")
            if kind == "thickness":
                vol = float(np.nansum(np.where(g.valid, g.z, np.nan))) * g.cell ** 2
                st.metric("Isopach volume", f"{vol / 1e6:,.1f} MCM")
        except ValueError as e:
            st.error(str(e))


@st.cache_resource(show_spinner="Building the 3D model…")
def _model(key, _project, _boundary, bkey, cell, dz, datum):
    from litholog.model3d import build_model

    return build_model(_project, cell or None, dz or None, datum=datum, boundary=_boundary)


def tab_model(project, boundary, key, title):
    from litholog.model3d import write_vtk
    from litholog.solid import VIEWS, build_solids, set_view, solid_figure

    c1, c2 = st.columns([1, 3])
    used, names = _codes(project)
    with c1:
        datum = st.selectbox("Correlate holes at equal", ["depth", "elevation"],
                             format_func=lambda d: {"depth": "Depth below ground (hard rock)",
                                                    "elevation": "Elevation (flat-lying sediments)"}[d])
        cell = st.number_input("Horizontal cell (m, 0 = auto)", 0.0, 1e5, 0.0, 50.0)
        dz = st.number_input("Vertical cell (m, 0 = auto)", 0.0, 1000.0, 0.0, 0.5)
        use_b = st.checkbox("Clip to study-area boundary", value=boundary is not None,
                            disabled=boundary is None, key="mb")
        show = st.multiselect("Units to show", used, default=used, format_func=names.get)
        cut = st.selectbox("Cut-away corner", ["none", "sw", "se", "ne", "nw"],
                           format_func=lambda c: "none" if c == "none" else f"remove {c.upper()} quarter")
        view = st.selectbox("View", ["free"] + list(VIEWS),
                            format_func=lambda v: "Free (drag to rotate)" if v == "free" else VIEWS[v]["title"])
        ve = st.number_input("Vertical exaggeration (0 = auto)", 0.0, 10000.0, 0.0, 5.0, key="mve")
        smooth = st.slider("Smoothing", 0.0, 3.0, 1.0, 0.25)
        st.markdown("**Specific yield** (for storage)")
        sy = {}
        for c in used:
            v = st.number_input(names[c], 0.0, 1.0, 0.0, 0.005, format="%.3f", key=f"sy_{c}")
            if v > 0:
                sy[c] = v
    b = boundary if use_b else None
    m = _model(key, project, b, "b" if b is not None else "", cell, dz, datum)
    with c2:
        only = show if set(show) != set(used) else None
        solids = build_solids(m, smooth, None if cut == "none" else cut, only)
        fig, _ = solid_figure(m, solids, project.legend, ve or None, title, sy=sy,
                              labels=len(project.ids) <= 30, cutaway=None if cut == "none" else cut)
        set_view(fig, "oblique_sw" if view == "free" else view)  # free view starts from the SW
        fig.update_layout(height=720)
        st.plotly_chart(fig, width="stretch")
        vols = m.volumes(sy)
        vols.insert(1, "name", [project.legend.get(c).name for c in vols["code"]])
        shown = ["name", "volume_mcm", "percent"] + (["specific_yield", "storage_mcm"] if sy else [])
        st.dataframe(vols[shown].rename(columns={"name": "Unit", "volume_mcm": "Volume (MCM)",
                                                 "percent": "%", "specific_yield": "Specific yield",
                                                 "storage_mcm": "Storage (MCM)"}).round(2),
                     width="stretch", hide_index=True)
        note = "MCM = million m³, from ground to the base of drilling"
        if m.boundary is not None:
            note += f", inside the study area ({m.boundary.area / 1e6:,.1f} km²)"
            if m.coverage is not None and m.coverage < 0.999:
                note += f"; {100 * (1 - m.coverage):.0f} % of it lies beyond the boreholes (extrapolated)"
        st.caption(note + ". Storage = volume × specific yield you enter (an estimate).")
        d1, d2, d3 = st.columns(3)
        with d1:
            html = _out(key, "model_3d.html")
            fig.write_html(html, include_plotlyjs=True)
            _download("⬇ Interactive 3D (HTML)", html, "text/html")
        with d2:
            st.download_button("⬇ Volumes (CSV)", vols.to_csv(index=False).encode(), "volumes.csv")
        with d3:
            _download("⬇ Model for ParaView (VTK)", write_vtk(m, _out(key, "model.vtk")))


def tab_help():
    st.markdown(f"""
### Getting started
1. **Upload** a LithoLog Excel workbook (get the template in the sidebar) or a **GMS borehole file**
   (`Name X Y Z Material`). Add a **legend** file to give your codes names and colours, and a
   **study-area shapefile** (zipped) to clip maps and the 3D model.
2. Work through the tabs; every result can be downloaded.

### What each tab does
* **Overview** – locations, data check (overlaps, gaps, unknown codes), legend.
* **Strip logs** – printable A4 logs: lithology, descriptions, well construction, water levels,
  downhole curves.
* **Cross-section** – correlated section through chosen holes (or along a line).
* **Fence** – 3D fence diagram joining neighbouring holes.
* **Maps** – contour maps (ground, top/base/depth/thickness of a unit, water table) with grids for GIS.
* **3D model** – smooth lithology solids, volumes and groundwater storage.

Correlation and interpolation between boreholes are interpretations: check them against your
geological knowledge. LithoLog v{litholog.__version__} · MIT licence.
""")


def main():
    loaded = sidebar()
    st.title("LithoLog")
    if loaded is None:
        st.info("⬅ Upload your borehole data in the sidebar, or choose **Demo data** to try LithoLog.")
        tab_help()
        return
    project, boundary, key = loaded
    title = project.name
    # One page at a time (Streamlit would otherwise redraw every tab on each click).
    pages = {
        "Overview": lambda: tab_overview(project, boundary),
        "Strip logs": lambda: tab_striplogs(project, key),
        "Cross-section": lambda: tab_section(project, key, title),
        "Fence": lambda: tab_fence(project, key, title),
        "Maps": lambda: tab_maps(project, boundary, key, title),
        "3D model": lambda: tab_model(project, boundary, key, title),
        "Help": tab_help,
    }
    page = st.radio("Page", list(pages), horizontal=True, label_visibility="collapsed", key="page")
    st.divider()
    pages[page]()


main()
