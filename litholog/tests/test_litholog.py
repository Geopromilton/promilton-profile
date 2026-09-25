from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from litholog import Legend, load_project, save_striplog, validate, write_template
from litholog.cli import main
from litholog.io import canonical_element, normalize

SAMPLE = Path(__file__).parents[1] / "examples" / "sample_project.xlsx"


def _write(path, **sheets):
    with pd.ExcelWriter(path) as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    return path


def test_header_normalization():
    assert normalize("Depth to water (m bgl)") == "depth_to_water"
    assert normalize("  Borehole ID ") == "borehole_id"
    assert canonical_element("Slotted pipe") == "screen"
    assert canonical_element("Gravel Pack") == "gravel_pack"


def test_template_roundtrip(tmp_path):
    p = write_template(tmp_path / "t.xlsx")
    proj = load_project(p)
    assert proj.ids == ["BH-01", "BH-02"]
    assert not [i for i in validate(proj) if i.level == "error"]
    bh = proj.borehole("BH-01")
    assert bh.depth == 60 and len(bh.lithology) == 4


def test_loose_headers_and_numeric_ids(tmp_path):
    p = _write(tmp_path / "x.xlsx",
               Collars=pd.DataFrame({"Well": [101], "Easting": [1.0], "Northing": [2.0], "TD": [10]}),
               Strata=pd.DataFrame({"Well": [101, 101], "Top": [0, 4], "Bottom": [4, 10],
                                    "Lith code": ["sand", "CLAY"]}))
    proj = load_project(p)
    assert proj.ids == ["101"]
    assert list(proj.borehole("101").lithology["code"]) == ["SAND", "CLAY"]


def test_validation_finds_problems(tmp_path):
    p = _write(tmp_path / "bad.xlsx",
               Boreholes=pd.DataFrame({"Borehole ID": ["A", "A"], "Total depth": [10, 10]}),
               Lithology=pd.DataFrame({"Borehole ID": ["A"] * 4, "From": [0, 3, 2, 8],
                                       "To": [3, 6, 5, 7], "Code": ["SAND", "XYZ", "CLAY", "GRA"]}))
    msgs = [str(i) for i in validate(load_project(p))]
    text = "\n".join(msgs)
    assert "more than once" in text
    assert "overlaps" in text
    assert "not in the legend" in text
    assert "To must be deeper" in text


def test_custom_legend_sheet(tmp_path):
    p = _write(tmp_path / "leg.xlsx",
               Lithology=pd.DataFrame({"BH": ["A"], "From": [0], "To": [5], "Code": ["MUR"]}),
               Legend=pd.DataFrame({"Code": ["MUR"], "Name": ["Murrum"], "Colour": ["#CC8855"],
                                    "Pattern": ["dots+diag"]}))
    leg = load_project(p).legend
    assert leg.get("mur").name == "Murrum" and leg.get("MUR").color == "#CC8855"
    assert "GRA" in leg  # defaults kept


def test_render_sample_pdf_and_paged_png(tmp_path):
    proj = load_project(SAMPLE)
    out = save_striplog(proj.borehole("TW-06"), proj.legend, tmp_path / "tw.pdf")
    assert out[0].stat().st_size > 10_000
    pages = save_striplog(proj.borehole("BW-05"), proj.legend, tmp_path / "bw.png", metres_per_page=50)
    assert len(pages) == 3 and all(p.exists() for p in pages)


def test_unknown_code_still_renders(tmp_path):
    p = _write(tmp_path / "u.xlsx",
               Lithology=pd.DataFrame({"BH": ["A"], "From": [0], "To": [5], "Code": ["???"]}))
    proj = load_project(p)
    assert save_striplog(proj.borehole("A"), Legend(), tmp_path / "u.png")[0].exists()


def test_cli(tmp_path, capsys):
    assert main(["template", str(tmp_path / "t.xlsx")]) == 0
    assert main(["validate", str(tmp_path / "t.xlsx")]) == 0
    assert main(["striplog", str(tmp_path / "t.xlsx"), "-o", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "BH-01.pdf").exists()
    assert (tmp_path / "out" / "all_boreholes.pdf").exists()
    assert main(["legend", "-o", str(tmp_path / "legend.png")]) == 0
    with pytest.raises(SystemExit):
        main(["striplog"])


def test_dates():
    from litholog.io import parse_date

    assert parse_date("2025-03-04").month == 3
    assert parse_date("04-03-2025").month == 3
    assert parse_date("") is pd.NaT


GMS = """Name\tX\tY\tZ\tMaterial
H1\t100\t200\t50\t1
H1\t100\t200\t48\t3
H1\t100\t200\t30\t4
H1\t100\t200\t25\t3
H1\t100\t200\t10\t3
H1\t100\t200\t0\t3
H2\t300\t400\t45\t1
H2\t300\t400\t40\t5
H2\t300\t400\t20\t5
"""


def test_gms_import_and_convert(tmp_path):
    src = tmp_path / "bores.txt"
    src.write_text(GMS)
    leg = tmp_path / "legend.csv"
    leg.write_text("Code,Name,Color,Pattern\n1,Top soil,#C9AE85,roots\n4,Fractured layer,#9FCBEA,waves+fractures\n")
    proj = load_project(src, legend=leg)
    h1 = proj.borehole("H1")
    assert (h1.elevation, h1.total_depth) == (50, 50)
    # repeated material rows (3,3,3) merge into one interval ending at the hole bottom
    assert h1.lithology[["from", "to", "code"]].values.tolist() == [
        [0, 2, "1"], [2, 20, "3"], [20, 25, "4"], [25, 50, "3"]]
    assert proj.borehole("H2").total_depth == 25
    assert proj.legend.get("4").name == "Fractured layer"
    assert main(["convert", str(src), str(tmp_path / "b.xlsx"), "-l", str(leg)]) == 0
    again = load_project(tmp_path / "b.xlsx")
    assert again.legend.get("1").name == "Top soil"
    assert again.borehole("H1").lithology["code"].tolist() == ["1", "3", "4", "3"]


# --- Milestone 2: correlation, sections, fences ---------------------------------

def _area(verts):
    import numpy as np

    v = np.asarray(verts, float)
    x, y = v[:, 0], v[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _gms_project(tmp_path):
    src = tmp_path / "b.txt"
    src.write_text(GMS + "H3\t500\t200\t40\t1\nH3\t500\t200\t38\t4\nH3\t500\t200\t30\t3\nH3\t500\t200\t-5\t5\n"
                   "H3\t500\t200\t-10\t5\n")
    return load_project(src)


def test_panel_tiles_without_gaps():
    from litholog.correlate import Unit, align, panel

    a = [Unit(100, 98, "1"), Unit(98, 70, "3"), Unit(70, 65, "4"), Unit(65, 40, "3"), Unit(40, 20, "5")]
    b = [Unit(90, 88, "1"), Unit(88, 60, "3"), Unit(60, 30, "5"), Unit(30, 25, "4"), Unit(25, 10, "5")]
    polys = panel(a, b, 0.0, 1000.0)
    # Panel area = trapezoid between the ground line and the base line.
    expected = 1000.0 * ((100 - 20) + (90 - 10)) / 2
    assert abs(sum(_area(v) for _, v in polys) - expected) < 1e-6 * expected
    pairs = align(a, b)
    assert pairs[0] == (0, 0)  # topsoil joins topsoil
    assert (1, 1) in pairs     # GBG joins GBG


def test_identical_holes_join_layer_for_layer():
    from litholog.correlate import Unit, panel

    a = [Unit(50, 45, "A"), Unit(45, 20, "B")]
    polys = panel(a, [Unit(40, 35, "A"), Unit(35, 10, "B")], 0, 100)
    assert [c for c, _ in polys] == ["A", "B"] and all(len(v) == 4 for _, v in polys)


def test_section_modes(tmp_path):
    from litholog.section import along_line, save_section, through_boreholes

    proj = _gms_project(tmp_path)
    line = through_boreholes(proj, ["H1", "H2", "H3"], "A-A'")
    assert [round(st.s) for st in line.stations] == [0, 283, 566]
    assert save_section(proj, line, tmp_path / "a.pdf").stat().st_size > 10_000
    near = along_line(proj, [(0, 200), (600, 200)], buffer=250, name="B-B'")
    assert [st.id for st in near.stations] == ["H1", "H2", "H3"]
    assert near.stations[1].offset != 0
    assert save_section(proj, near, tmp_path / "b.png", page="A4", ve=10).exists()
    with pytest.raises(ValueError):
        along_line(proj, [(0, 5000), (600, 5000)], buffer=10)


def test_fence_networks(tmp_path):
    from litholog.fence import network_edges, save_fence

    proj = _gms_project(tmp_path)
    mst = network_edges(proj, method="mst")
    assert len(mst) == 2  # spanning tree of 3 holes
    assert len(network_edges(proj, method="delaunay", max_factor=10)) == 3
    files = save_fence(proj, mst, tmp_path / "f.png", views=[-60, 30])
    assert len(files) == 2 and all(f.exists() for f in files)


def test_section_and_fence_cli(tmp_path):
    proj_file = tmp_path / "b.txt"
    proj_file.write_text(GMS + "H3\t500\t200\t40\t1\nH3\t500\t200\t-10\t5\n")
    sec = tmp_path / "sections.csv"
    sec.write_text("Section,Borehole ID\nA-A',H1\nA-A',H2\nB-B',H2\nB-B',H3\n")
    assert main(["section", str(proj_file), "-s", str(sec), "-o", str(tmp_path / "s")]) == 0
    assert (tmp_path / "s" / "all_sections.pdf").exists()
    assert main(["section", str(proj_file), "-b", "H1", "H3", "-o", str(tmp_path / "s"), "-f", "png"]) == 0
    assert main(["fence", str(proj_file), "-o", str(tmp_path / "f.pdf")]) == 0
    assert main(["fence", str(proj_file), "--network", "sections", "-s", str(sec),
                 "-o", str(tmp_path / "g.png")]) == 0


# --- Milestone 3: grids, maps, block model ---------------------------------------

def _grid_project(tmp_path):
    import numpy as np

    rows = ["Name\tX\tY\tZ\tMaterial"]
    rng = np.random.default_rng(1)
    for k in range(12):
        x, y = rng.uniform(0, 2000, 2)
        g = 100 + x / 100
        rows += [f"B{k}\t{x:.1f}\t{y:.1f}\t{g:.1f}\t1", f"B{k}\t{x:.1f}\t{y:.1f}\t{g - 3:.1f}\t4",
                 f"B{k}\t{x:.1f}\t{y:.1f}\t{g - 13:.1f}\t3", f"B{k}\t{x:.1f}\t{y:.1f}\t{g - 40:.1f}\t3"]
    f = tmp_path / "g.txt"
    f.write_text("\n".join(rows) + "\n")
    return load_project(f), f


def test_borehole_values(tmp_path):
    from litholog.grid import borehole_values

    proj, _ = _grid_project(tmp_path)
    th = borehole_values(proj, "thickness:4")["value"]
    assert (abs(th - 10) < 1e-6).all()
    assert (abs(borehole_values(proj, "depth:4")["value"] - 3) < 1e-6).all()
    assert borehole_values(proj, "top:9")["value"].isna().all()
    with pytest.raises(ValueError):
        borehole_values(proj, "thickness")


@pytest.mark.parametrize("method", ["idw", "linear", "kriging"])
def test_interpolators_honour_data(method):
    import numpy as np

    from litholog.grid import interpolate

    px, py = np.array([0.0, 100, 0, 100]), np.array([0.0, 0, 100, 100])
    pv = np.array([1.0, 2, 3, 4])
    z = interpolate(px, py, pv, np.array([0.0, 50, 100]), np.array([0.0, 50, 100]), method)
    assert abs(z[0, 0] - 1) < 1e-6 and abs(z[2, 2] - 4) < 1e-6
    assert 1 <= z[1, 1] <= 4


def test_isopach_and_block_model_volumes_agree(tmp_path):
    import numpy as np

    from litholog.grid import grid_attribute, write_ascii_grid
    from litholog.model3d import build_model, write_vtk

    proj, _ = _grid_project(tmp_path)
    g, _ = grid_attribute(proj, "thickness:4", cell=50)
    area = np.isfinite(g.z).sum() * g.cell ** 2
    assert abs(np.nanmean(g.z) - 10) < 1e-6
    m = build_model(proj, cell=50, dz=1.0)
    v = m.volumes({"4": 0.02}).set_index("code")
    # 10 m layer everywhere: model volume ~ 10 m x model area
    model_area = (m.lith >= 0).any(0).sum() * m.cell ** 2
    assert abs(v.loc["4", "volume_m3"] / model_area - 10) < 1.0
    assert abs(v.loc["4", "storage_m3"] - 0.02 * v.loc["4", "volume_m3"]) < 1
    assert area > 0
    # model reproduces a borehole log at the hole
    bh = proj.borehole("B0")
    assert m.code_at(bh.x, bh.y, bh.elevation - 8) == "4"
    assert m.code_at(bh.x, bh.y, bh.elevation - 30) == "3"
    asc = write_ascii_grid(g, tmp_path / "t.asc").read_text().splitlines()
    assert asc[0].startswith("ncols") and len(asc) == 6 + len(g.y)
    vtk = write_vtk(m, tmp_path / "m.vtk").read_text()
    assert "STRUCTURED_POINTS" in vtk and f"DIMENSIONS {len(m.x)} {len(m.y)} {len(m.z)}" in vtk


def test_map_and_model_cli(tmp_path):
    _, f = _grid_project(tmp_path)
    assert main(["map", str(f), "-a", "ground", "thickness:4", "top:3", "-m", "kriging",
                 "-o", str(tmp_path / "maps"), "-f", "png"]) == 0
    assert (tmp_path / "maps" / "thickness_4.png").exists()
    assert (tmp_path / "maps" / "thickness_4.asc").exists()
    assert main(["model", str(f), "--cell", "100", "--sy", "4=0.02", "--only", "4", "--style", "both",
                 "--views", "oblique_sw", "top", "-o", str(tmp_path / "model"), "-f", "png"]) == 0
    for name in ("block_model.png", "block_model_4.png", "slices.png", "volumes.csv", "model.vtk",
                 "solid_3d.html", "solid_top.png", "solid_4_3d.html"):
        assert (tmp_path / "model" / name).exists()


# --- Study-area boundary (shapefile) ---------------------------------------------

def _write_boundary(path, rings, epsg=None):
    import shapefile

    w = shapefile.Writer(str(path), shapeType=shapefile.POLYGON)
    w.field("Id", "N")
    w.poly(rings)
    w.record(1)
    w.close()
    if epsg:
        from pyproj import CRS

        path.with_suffix(".prj").write_text(CRS.from_epsg(epsg).to_wkt("WKT1_ESRI"))


def test_boundary_area_hole_and_mask(tmp_path):
    import numpy as np

    from litholog.boundary import load_boundary

    outer = [(0, 0), (0, 100), (100, 100), (100, 0), (0, 0)]
    hole = [(40, 40), (60, 40), (60, 60), (40, 60), (40, 40)]
    _write_boundary(tmp_path / "b.shp", [outer, hole])
    b = load_boundary(tmp_path / "b.shp")
    assert abs(b.area - (10000 - 400)) < 1e-6
    assert list(b.contains([[10, 10], [50, 50], [150, 50]])) == [True, False, False]
    m = b.mask(np.arange(5, 100, 10.0), np.arange(5, 100, 10.0))
    assert m.sum() == 100 - 4


def test_boundary_auto_utm_zone_and_clipping(tmp_path):
    import numpy as np
    from pyproj import Transformer

    from litholog.boundary import load_boundary
    from litholog.grid import grid_attribute
    from litholog.model3d import build_model

    proj, _ = _grid_project(tmp_path)
    # Shift the synthetic holes into UTM 43N near 77.6 E, 8.4 N.
    proj.boreholes["x"] += 780000
    proj.boreholes["y"] += 930000
    ring43 = np.array([(779500, 929500), (779500, 932500), (782500, 932500), (782500, 929500)])
    x44, y44 = Transformer.from_crs(32643, 32644, always_xy=True).transform(ring43[:, 0], ring43[:, 1])
    _write_boundary(tmp_path / "sa.shp", [list(zip(x44, y44)) + [(x44[0], y44[0])]], epsg=32644)
    b = load_boundary(tmp_path / "sa.shp", near=(780000, 782000, 930000, 932000))
    assert "EPSG:32643" in b.crs_note
    assert abs(b.area - 9e6) / 9e6 < 0.01
    g, _ = grid_attribute(proj, "thickness:4", cell=100, boundary=b)
    assert g.coverage is not None and g.coverage < 1
    assert abs(g.valid.sum() * 100 ** 2 - b.area) / b.area < 0.05
    m = build_model(proj, cell=100, dz=1.0, boundary=b)
    area = (m.lith >= 0).any(0).sum() * 100 ** 2
    assert abs(area - b.area) / b.area < 0.05
    v = m.volumes().set_index("code")
    assert abs(v.loc["4", "volume_m3"] / area - 10) < 1.0


# --- Smooth solids ------------------------------------------------------------------

def test_smooth_solids_and_views(tmp_path):
    import numpy as np

    from litholog.model3d import build_model
    from litholog.solid import VIEWS, build_solids, export_solids, solid_figure

    proj, _ = _grid_project(tmp_path)
    m = build_model(proj, cell=100, dz=1.0)
    solids = build_solids(m)
    assert {s.code for s in solids} == {"1", "4", "3"}
    for s in solids:
        assert len(s.faces) > 0
        assert m.x[0] - m.cell <= s.verts[:, 0].min() and s.verts[:, 0].max() <= m.x[-1] + m.cell
        assert m.z[0] - m.dz <= s.verts[:, 2].min() and s.verts[:, 2].max() <= m.z[-1] + m.dz
    only = build_solids(m, only=["4"])
    assert [s.code for s in only] == ["4"]
    cut = build_solids(m, cutaway="sw")
    assert sum(len(s.faces) for s in cut) > 0
    fig, ve = solid_figure(m, solids, proj.legend)
    assert ve >= 1 and len(fig.data) >= 3
    files = export_solids(m, proj.legend, tmp_path / "out", views=["oblique_sw", "front"])
    assert (tmp_path / "out" / "solid_3d.html").stat().st_size > 100_000
    assert set(VIEWS) >= {"top", "front", "back", "left", "right", "oblique_sw"}
    assert files[0].name == "solid_3d.html"


# --- Browser app -------------------------------------------------------------------

def test_app_pages_run_on_demo_data():
    pytest.importorskip("streamlit")
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    app = Path(__file__).parents[1] / "litholog" / "app.py"
    at = AppTest.from_file(str(app), default_timeout=300)
    at.run()
    assert not at.exception
    at.sidebar.radio[0].set_value("Demo data (synthetic)").run()
    for page in ["Overview", "Strip logs", "Cross-section", "Fence", "Maps", "3D model", "Help"]:
        at.radio(key="page").set_value(page).run()
        assert not at.exception, (page, [e.message for e in at.exception])
        assert not at.error, (page, [e.value for e in at.error])


# --- Studio (desktop) ----------------------------------------------------------------

def test_project_file_roundtrip(tmp_path):
    from litholog.studio.projectfile import load, save

    data = tmp_path / "data" / "bores.xlsx"
    data.parent.mkdir()
    data.write_text("placeholder")
    p = save(tmp_path / "study.llproj", "Study", data, None, None, {"ve": 25, "specific_yield": {"4": 0.015}})
    pf = load(p)
    assert Path(pf["data"]) == data.resolve() and pf["name"] == "Study"
    assert pf["settings"]["specific_yield"] == {"4": 0.015}
    assert '"data/bores.xlsx"' in p.read_text()  # stored relative to the project file
    (tmp_path / "bad.llproj").write_text('{"format": "x"}')
    with pytest.raises(ValueError):
        load(tmp_path / "bad.llproj")


# --- Aquifer, property, stratigraphy, hydrochemistry, fractures ---------------------

SAMPLE = Path(__file__).parents[1] / "examples" / "sample_project.xlsx"


def test_wells_long_wide_and_latlon(tmp_path):
    from pyproj import Transformer

    from litholog.aquifer import load_wells

    lon, lat = Transformer.from_crs(32643, 4326, always_xy=True).transform([651000, 652000], [1688000, 1687000])
    wide = pd.DataFrame({"Station": ["A", "B"], "Latitude": lat, "Longitude": lon,
                         "Pre-monsoon 2023": [12.0, 9.0], "Post-monsoon 2023": [5.0, 3.5]})
    wide.to_csv(tmp_path / "wide.csv", index=False)
    w = load_wells(tmp_path / "wide.csv", crs="EPSG:32643")
    assert w.readings == ["Pre-monsoon 2023", "Post-monsoon 2023"]
    assert abs(w.table["x"].iloc[0] - 651000) < 0.01 and "converted" in w.note
    long = pd.DataFrame({"Well": ["A", "A", "B", "B"], "X": [1, 1, 5, 5], "Y": [1, 1, 5, 5],
                         "Date": ["May", "Nov", "May", "Nov"], "DTW (m bgl)": [10, 4, 8, 3]})
    long.to_excel(tmp_path / "long.xlsx", index=False)
    w2 = load_wells(tmp_path / "long.xlsx")
    assert w2.readings == ["May", "Nov"] and list(w2.values("Nov")["dtw"]) == [4, 3]


def test_saturated_volume_below_water_table(tmp_path):
    from litholog.aquifer import Wells, saturated_volumes, water_table
    from litholog.model3d import build_model

    proj, _ = _grid_project(tmp_path)  # topsoil 0-3 m, unit 4 3-13 m, unit 3 below; ground = 100 + x/100
    m = build_model(proj, cell=100, dz=1.0)
    b = proj.boreholes
    t = pd.DataFrame({"well_id": b["borehole_id"], "x": b["x"], "y": b["y"], "ground": np.nan, "dry": 8.0})
    wt = water_table(m, Wells(t, ["dry"]), "dry")
    v = saturated_volumes(m, wt, {"4": 0.1}).set_index("code")
    # water at 8 m depth: unit 4 (3-13 m) is half saturated, topsoil dry, unit 3 fully saturated
    assert abs(v.loc["4", "saturated_pct"] - 50) < 12
    assert v.loc["1", "saturated_pct"] < 5 and v.loc["3", "saturated_pct"] > 95
    assert abs(v.loc["4", "storage_mcm"] - 0.1 * v.loc["4", "saturated_mcm"]) < 1e-9


def test_property_model_honours_data():
    from litholog.io import load_project
    from litholog.model3d import build_model
    from litholog.property3d import build_property, parameters

    p = load_project(SAMPLE)
    assert "Resistivity" in parameters(p)
    m = build_model(p, datum="elevation")
    pm = build_property(p, m, "Resistivity", datum="elevation")
    s = pm.samples.iloc[len(pm.samples) // 2]
    k, j, i = (int(np.argmin(abs(a - v))) for a, v in ((m.z, s.z), (m.y, s.y), (m.x, s.x)))
    if np.isfinite(pm.values[k, j, i]):
        assert abs(np.log10(pm.values[k, j, i]) - np.log10(s.value)) < 0.5
    assert pm.volume_between(hi=pm.stats()["max"]) > 0


def test_strat_model_orders_surfaces(tmp_path):
    from litholog.strat import build_strat_model

    proj, _ = _grid_project(tmp_path)
    m = build_strat_model(proj, ["1", "4", "3"], cell=100, dz=1.0)
    s1, s4, s3 = (m.surfaces[c] for c in ("1", "4", "3"))
    assert np.all(s4 <= s1 + 1e-9) and np.all(s3 <= s4 + 1e-9)
    v = m.volumes().set_index("code")
    area = (m.lith >= 0).any(0).sum() * m.cell ** 2
    assert abs(v.loc["4", "volume_m3"] / area - 10) < 1.5  # 10 m thick unit


def test_hydrochem_indices_and_diagrams(tmp_path):
    from litholog.hydrochem import analyse, load_chemistry, report, ussl_class, wilcox_class

    df = pd.DataFrame({"Sample": ["A", "B"], "Ca (mg/L)": [40.078, 80], "Mg (mg/L)": [24.305, 20],
                       "Na (mg/L)": [45.98, 200], "K": [0, 5], "HCO3": [183.05, 300], "CO3": [0, 0],
                       "Cl": [70.906, 250], "SO4": [0, 50], "EC (uS/cm)": [500, 1800], "TDS": [320, 1150]})
    d = load_chemistry(df)
    r = analyse(d)
    # sample A: Ca 2, Mg 2, Na 2 meq/L; HCO3 3, Cl 2 → SAR = 2/sqrt(2) = 1.41
    assert abs(r["SAR"][0] - 1.41) < 0.01
    assert abs(r["ionic_balance_pct"][0] - 9.09) < 0.05
    assert r["water_type"][0] in ("Ca-HCO3", "Mg-HCO3", "Na-HCO3")
    assert ussl_class(500, 1.4) == "C2S1" and wilcox_class(1800, 20) == "Permissible"
    files = report(d, tmp_path / "chem")
    names = {f.name for f in files}
    assert {"piper.png", "durov.png", "stiff.png", "ussl.png", "wilcox.png", "hydrochemistry.pdf"} <= names


def test_fractures_rose_stereonet_and_log_track(tmp_path):
    from litholog.fractures import _pole_xy, fracture_report, table
    from litholog.io import load_project
    from litholog.striplog import save_striplog

    # plane dipping 90 toward east: pole horizontal toward west, on the primitive
    x, y = _pole_xy(np.array([90.0]), np.array([90.0]))
    assert abs(x[0] + 1) < 1e-9 and abs(y[0]) < 1e-9
    p = load_project(SAMPLE)
    assert len(table(p)) > 10
    assert fracture_report(p, tmp_path / "fr.png").exists()
    assert save_striplog(p.borehole("BW-01"), p.legend, tmp_path / "log.png")[0].exists()


def test_log_section_and_new_cli(tmp_path):
    out = tmp_path / "o"
    assert main(["section", str(SAMPLE), "-b", "BW-01", "BW-03", "--style", "logs", "--curve", "Resistivity",
                 "-o", str(out), "-f", "png"]) == 0
    assert main(["fractures", str(SAMPLE), "-o", str(out / "fr.pdf")]) == 0
    assert main(["strat", str(SAMPLE), "--order", "RSOIL", "WGRA", "GRA", "-o", str(out / "strat")]) == 0
    assert (out / "strat" / "volumes.csv").exists()


def _fractured_project(tmp_path):
    """Hard-rock profile with two thin water-bearing fracture zones (code 4) whose depth varies
    from hole to hole, inside massive rock (3): the case an indicator model breaks up."""
    rows = ["Name\tX\tY\tZ\tMaterial"]
    rng = np.random.default_rng(7)
    for k in range(16):
        x, y = rng.uniform(0, 3000, 2)
        g = 120 + x / 200
        d1, d2 = rng.uniform(15, 35), rng.uniform(50, 75)        # fracture zones wander in depth
        tops = [(0, "1"), (3, "2"), (10, "3"), (d1, "4"), (d1 + 3, "3"), (d2, "4"), (d2 + 3, "3"), (100, "3")]
        rows += [f"B{k}\t{x:.1f}\t{y:.1f}\t{g - d:.2f}\t{m}" for d, m in tops]
    f = tmp_path / "fr.txt"
    f.write_text("\n".join(rows) + "\n")
    return load_project(f)


def test_horizon_model_keeps_thin_repeated_layers_continuous(tmp_path):
    from litholog.horizons import build_horizon_model, horizon_volumes
    from litholog.solid import build_solids

    proj = _fractured_project(tmp_path)
    m = build_horizon_model(proj, cell=100)
    hv = horizon_volumes(m)
    zones = hv[hv["code"] == "4"]
    assert len(zones) == 2 and (zones["holes_present"] == 16).all()      # both zones traced in every hole
    assert (zones["area_present_pct"] > 99).all()                         # continuous sheets, no lenses
    area = m.inside.sum() * m.cell ** 2
    assert np.allclose(zones["volume_mcm"] * 1e6 / area, 3.0, atol=0.05)  # 3 m thick each
    # surfaces never cross and the stack reaches the base of drilling
    for k in range(len(m.horizons)):
        assert np.all(m.h_bot[k][m.inside] <= m.h_top[k][m.inside] + 1e-9)
    assert np.allclose(hv["volume_mcm"].sum() * 1e6, (np.where(m.inside, m.ground - m.h_bot[-1], 0)).sum()
                       * m.cell ** 2, rtol=1e-6)
    assert {s.code for s in build_solids(m, cutaway="sw")} == {"1", "2", "3", "4"}


def test_dem_ascii_and_geotiff(tmp_path):
    import tifffile

    from litholog.dem import load_dem, sample

    z = np.arange(12, dtype=float).reshape(3, 4) * 10     # row 0 = north
    (tmp_path / "d.asc").write_text("ncols 4\nnrows 3\nxllcorner 1000\nyllcorner 2000\ncellsize 10\n"
                                    "NODATA_value -9999\n" + "\n".join(" ".join(f"{v:g}" for v in r) for r in z))
    a = load_dem(tmp_path / "d.asc")
    assert sample(a, [1005], [2025])[0] == 0            # centre of the NW cell
    assert sample(a, [1010], [2020])[0] == 25           # between four cells
    geokeys = (1, 1, 0, 1, 3072, 0, 1, 32643)
    tifffile.imwrite(tmp_path / "d.tif", z.astype(np.float32),
                     extratags=[(33550, "d", 3, (10.0, 10.0, 0.0)), (33922, "d", 6, (0, 0, 0, 1000, 2030, 0)),
                                (34735, "H", len(geokeys), geokeys)])
    t = load_dem(tmp_path / "d.tif")
    assert t.crs.to_epsg() == 32643
    assert np.isclose(sample(t, [1010], [2020])[0], 25)
    assert np.isnan(sample(t, [0], [0])[0])


def test_boundary_kml_kmz_geojson(tmp_path):
    import json
    import zipfile

    from litholog.boundary import load_boundary

    outer = [(77.50, 8.30), (77.60, 8.30), (77.60, 8.40), (77.50, 8.40), (77.50, 8.30)]
    hole = [(77.54, 8.34), (77.56, 8.34), (77.56, 8.36), (77.54, 8.36), (77.54, 8.34)]
    c = lambda r: " ".join(f"{x},{y},0" for x, y in r)  # noqa: E731
    kml = ('<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><Polygon>'
           f'<outerBoundaryIs><LinearRing><coordinates>{c(outer)}</coordinates></LinearRing></outerBoundaryIs>'
           f'<innerBoundaryIs><LinearRing><coordinates>{c(hole)}</coordinates></LinearRing></innerBoundaryIs>'
           '</Polygon></Placemark></Document></kml>')
    (tmp_path / "b.kml").write_text(kml)
    with zipfile.ZipFile(tmp_path / "b.kmz", "w") as z:
        z.writestr("doc.kml", kml)
    (tmp_path / "b.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [outer, hole]}}]}))
    areas = []
    for name in ("b.kml", "b.kmz", "b.geojson"):
        b = load_boundary(tmp_path / name, crs="EPSG:32643")
        assert len(b.rings) == 2
        areas.append(b.area)
    assert np.allclose(areas, areas[0]) and 110e6 < areas[0] < 125e6     # ~11 km x 11 km minus the hole
    # without --crs: lon/lat is matched to the boreholes' UTM zone automatically
    bx0, bx1, by0, by1 = load_boundary(tmp_path / "b.kml", crs="EPSG:32643").bbox
    auto = load_boundary(tmp_path / "b.geojson", near=(bx0 + 1000, bx1 - 1000, by0 + 1000, by1 - 1000))
    assert "EPSG:32643" in auto.crs_note and np.isclose(auto.area, areas[0])


def test_legend_save_roundtrip(tmp_path):
    from litholog.io import load_legend, save_legend

    lg = Legend().updated([{"code": "4", "name": "Fractured zone", "color": "#123456", "pattern": "waves+fractures"}])
    save_legend(lg, tmp_path / "l.csv", ["4", "GRA"])
    back = load_legend(tmp_path / "l.csv")
    assert back.get("4").color == "#123456" and back.get("4").pattern == "waves+fractures"
    assert back.get("GRA").name == Legend().get("GRA").name


def test_cli_model_horizons_with_dem(tmp_path):
    proj = _fractured_project(tmp_path)
    b = proj.boreholes
    x0, y0 = b["x"].min() - 500, b["y"].min() - 500
    nx = ny = 50
    (tmp_path / "dem.asc").write_text(f"ncols {nx}\nnrows {ny}\nxllcorner {x0}\nyllcorner {y0}\ncellsize 100\n"
                                      "NODATA_value -9999\n" + "\n".join(" ".join("130" for _ in range(nx))
                                                                          for _ in range(ny)))
    out = tmp_path / "m"
    assert main(["model", str(tmp_path / "fr.txt"), "--dem", str(tmp_path / "dem.asc"), "--rectify",
                 "--views", "top", "--style", "smooth", "-o", str(out)]) == 0
    hv = pd.read_csv(out / "horizons.csv")
    assert (hv[hv["code"] == 4]["holes_present"] == 16).all()


def test_crossval_scoring_and_report(tmp_path):
    from litholog.validation import score, validation_report

    actual = [(0, 3, "1"), (3, 10, "3"), (10, 13, "4"), (13, 30, "3")]
    same = score(actual, actual, ["1", "3", "4"])
    assert same[0]["match_pct"] == 100 and all(u["detected"] == u["occurrences"] for u in same[1])
    shifted = score(actual, [(0, 3, "1"), (3, 12, "3"), (12, 15, "4"), (15, 30, "3")], ["4"])
    u4 = shifted[1][0]
    assert u4["detected"] == 1 and abs(u4["top_error_m"] - 2) < 1e-9 and 80 < shifted[0]["match_pct"] < 90
    missed = score(actual, [(0, 3, "1"), (3, 30, "3")], ["4"])[1][0]
    assert missed["detected"] == 0 and missed["false_alarms"] == 0

    # fracture zones whose depth changes smoothly across the site (spatially continuous, as the
    # horizon method assumes); random, uncorrelated depths would be unpredictable by any method
    rows = ["Name\tX\tY\tZ\tMaterial"]
    rng = np.random.default_rng(3)
    for k in range(16):
        x, y = rng.uniform(0, 3000, 2)
        g, d1, d2 = 120 + x / 200, 20 + x / 300, 55 + y / 250
        tops = [(0, "1"), (3, "2"), (10, "3"), (d1, "4"), (d1 + 3, "3"), (d2, "4"), (d2 + 3, "3"), (100, "3")]
        rows += [f"B{k}\t{x:.1f}\t{y:.1f}\t{g - d:.2f}\t{m}" for d, m in tops]
    (tmp_path / "smooth.txt").write_text("\n".join(rows) + "\n")
    proj = load_project(tmp_path / "smooth.txt")
    r = validation_report(proj, tmp_path / "cv", methods=("horizons_idw", "voxel", "nearest"), target="4",
                          volumes=False)
    s = r["summary"].set_index("method")
    assert set(s.index) == {"horizons_idw", "voxel", "nearest"} and (s["holes"] == 16).all()
    u = r["per_unit"].set_index(["method", "code"])
    # continuous fracture zones: the horizon model finds them at hidden boreholes, the voxel vote does not
    assert u.loc[("horizons_idw", "4"), "detection_pct"] > u.loc[("voxel", "4"), "detection_pct"]
    assert u.loc[("horizons_idw", "4"), "detection_pct"] >= 90
    assert (tmp_path / "cv" / "validation.pdf").exists()
