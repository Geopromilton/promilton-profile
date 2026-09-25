from pathlib import Path

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
    assert main(["model", str(f), "--cell", "100", "--sy", "4=0.02", "--only", "4",
                 "-o", str(tmp_path / "model"), "-f", "png"]) == 0
    for name in ("block_model.png", "block_model_4.png", "slices.png", "volumes.csv", "model.vtk"):
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
