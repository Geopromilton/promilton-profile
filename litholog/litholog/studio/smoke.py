"""Headless self-test: start the window, load the demo, build the model, draw, quit."""

from __future__ import annotations

import sys
import time


def run(timeout: float = 300) -> int:
    from PySide6.QtWidgets import QApplication

    from . import theme
    from .mainwindow import DEMO, MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    theme.apply(app)
    w = MainWindow()
    w.show()
    w.load(str(DEMO), name="Demo")
    t0 = time.time()
    while w.model is None and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.05)
    ok = w.model is not None and len(w.viewer.units) > 0
    if ok:
        w.show_striplog(bid=w.project.ids[0])
        app.processEvents()
        ok = bool(w.viewer.legend.items)          # legend bar filled with volumes
        c = w.model.codes[0]                       # recolour a layer as the dialog would
        w.project.legend = w.project.legend.updated([{"code": c, "color": "#FF00FF"}])
        w.viewer.set_unit_color(c, "#FF00FF")
        w.set_theme("light")
        w.set_theme("dark")
        app.processEvents()
    print("LithoLog Studio smoke test:", "OK" if ok else "FAILED")
    w._saved_key = w._state_key()     # nothing to save in a self-test
    w.close()
    return 0 if ok else 1


def check(report_path: str) -> int:
    """Bundle completeness check without a display: every engine step + GUI imports.

    Writes a report (a windowed .exe has no console) and returns 0 when all steps pass.
    """
    import tempfile
    import traceback
    from pathlib import Path

    lines, ok = [], True

    def step(name, fn):
        nonlocal ok
        try:
            fn()
            lines.append(f"OK    {name}")
        except Exception:  # noqa: BLE001 - reported
            ok = False
            lines.append(f"FAIL  {name}\n{traceback.format_exc()}")

    out = Path(tempfile.mkdtemp(prefix="litholog_check_"))
    state = {}

    def load():
        from ..io import load_project
        from .mainwindow import DEMO

        state["p"] = load_project(DEMO)

    def logs():
        from ..striplog import save_striplog

        p = state["p"]
        save_striplog(p.borehole(p.ids[0]), p.legend, out / "log.pdf")

    def section():
        from ..section import save_section, through_boreholes

        p = state["p"]
        save_section(p, through_boreholes(p, p.ids[:3]), out / "sec.pdf")

    def maps():
        from ..grid import grid_attribute
        from ..maps import save_map

        g, v = grid_attribute(state["p"], "ground", "kriging")
        save_map(g, v, "ground", out / "map.pdf")

    def model():
        from ..model3d import build_model
        from ..solid import build_solids

        state["m"] = build_model(state["p"])
        assert build_solids(state["m"], cutaway="sw")

    def horizons():
        from ..horizons import build_horizon_model, horizon_volumes
        from ..solid import build_solids

        m = build_horizon_model(state["p"])
        assert len(horizon_volumes(m)) and build_solids(m, cutaway="sw")

    def validation():
        from ..validation import validation_report

        r = validation_report(state["p"], out / "cv", methods=("horizons_idw", "nearest"), volumes=False)
        assert len(r["summary"]) == 2

    def dem_and_boundaries():
        import json

        import numpy as np

        from ..boundary import load_boundary
        from ..dem import load_dem, sample

        (out / "d.asc").write_text("ncols 3\nnrows 2\nxllcorner 0\nyllcorner 0\ncellsize 10\n"
                                   "NODATA_value -9999\n1 2 3\n4 5 6\n")
        assert np.isfinite(sample(load_dem(out / "d.asc"), [10], [10])).all()
        ring = [[77.5, 8.3], [77.6, 8.3], [77.6, 8.4], [77.5, 8.3]]
        (out / "b.geojson").write_text(json.dumps({"type": "Polygon", "coordinates": [ring]}))
        load_boundary(out / "b.geojson", crs="EPSG:32643")
        coords = " ".join(f"{x},{y},0" for x, y in ring)
        (out / "b.kml").write_text('<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Polygon>'
                                   f'<outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates>'
                                   '</LinearRing></outerBoundaryIs></Polygon></Placemark></kml>')
        load_boundary(out / "b.kml", crs="EPSG:32643")
        import tifffile  # noqa: F401 - GeoTIFF DEMs

    def gui_imports():
        import pyvista  # noqa: F401
        import pyvistaqt  # noqa: F401
        import qtawesome  # noqa: F401
        import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
        from PySide6 import QtSvg, QtWidgets  # noqa: F401

        from . import legendbar, logo, mainwindow, viewer3d  # noqa: F401

    def reproject():
        from pyproj import Transformer

        x, y = Transformer.from_crs(32644, 32643, always_xy=True).transform(130000, 930000)
        assert 790000 < x < 800000

    def analysis():
        import pandas as pd

        from ..aquifer import saturated_volumes, water_table, wells_from_project
        from ..fractures import fracture_figure
        from ..hydrochem import analyse, load_chemistry, piper
        from ..property3d import build_property
        from ..strat import build_strat_model

        p, m = state["p"], state["m"]
        saturated_volumes(m, water_table(m, wells_from_project(p)))
        build_property(p, m, "Resistivity")
        build_strat_model(p, ["RSOIL", "WGRA", "GRA"])
        fracture_figure(p)
        chem = load_chemistry(pd.DataFrame({"Ca": [40], "Mg": [24], "Na": [46], "K": [0], "HCO3": [183],
                                            "Cl": [71], "SO4": [10], "EC": [500]}))
        analyse(chem)
        piper(chem)

    for name, fn in [("load demo", load), ("strip log PDF", logs), ("cross-section PDF", section),
                     ("kriged map PDF", maps), ("3D model + smooth solids", model),
                     ("horizon model + solids", horizons), ("DEM, KML, GeoJSON", dem_and_boundaries), ("cross-validation report", validation),
                     ("aquifer, property, strat, fractures, chemistry", analysis),
                     ("GUI libraries (Qt, VTK, icons)", gui_imports), ("reprojection (PROJ data)", reproject)]:
        step(name, fn)
    Path(report_path).write_text("\n".join(lines) + f"\n\nRESULT: {'PASS' if ok else 'FAIL'}\n")
    return 0 if ok else 1
