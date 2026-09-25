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
