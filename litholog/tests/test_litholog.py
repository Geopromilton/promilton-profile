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
