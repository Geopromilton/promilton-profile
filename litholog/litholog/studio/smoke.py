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
    print("LithoLog Studio smoke test:", "OK" if ok else "FAILED")
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

    def gui_imports():
        import pyvista  # noqa: F401
        import pyvistaqt  # noqa: F401
        import qtawesome  # noqa: F401
        import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
        from PySide6 import QtWidgets  # noqa: F401

        from . import mainwindow, viewer3d  # noqa: F401

    def reproject():
        from pyproj import Transformer

        x, y = Transformer.from_crs(32644, 32643, always_xy=True).transform(130000, 930000)
        assert 790000 < x < 800000

    for name, fn in [("load demo", load), ("strip log PDF", logs), ("cross-section PDF", section),
                     ("kriged map PDF", maps), ("3D model + smooth solids", model),
                     ("GUI libraries (Qt, VTK, icons)", gui_imports), ("reprojection (PROJ data)", reproject)]:
        step(name, fn)
    Path(report_path).write_text("\n".join(lines) + f"\n\nRESULT: {'PASS' if ok else 'FAIL'}\n")
    return 0 if ok else 1
