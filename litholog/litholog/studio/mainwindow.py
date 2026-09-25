"""LithoLog Studio main window."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDockWidget, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSlider, QTableWidget, QTableWidgetItem,
                               QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import __version__
from . import theme
from .viewer3d import Viewer3D
from .widgets import FigureDoc, Job, Ribbon

DEMO = Path(__file__).resolve().parents[1] / "data" / "sample_project.xlsx"
MAP_KINDS = {"ground": "Ground elevation", "top": "Top of unit", "base": "Base of unit",
             "depth": "Depth to unit", "thickness": "Thickness (isopach)", "water": "Water-table elevation",
             "dtw": "Depth to water", "total_depth": "Drilled depth"}


def swatch(color: str, size=14) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(QColor(color))
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LithoLog Studio {__version__}")
        from .logo import app_icon

        self.setWindowIcon(app_icon())
        self.resize(1680, 980)
        self.pool = QThreadPool.globalInstance()
        self.project = None
        self.boundary = None
        self.model = None
        self.solids = None
        self.data_path = None
        self.legend_path = None
        self.boundary_path = None
        self.dem = None
        self.dem_path = None
        self.layer_state = {}    # code -> {"visible": bool, "opacity": 0-1}
        self.hz_state = {}       # horizon index -> visible
        self._redo = {}          # document -> callable that redraws it (after legend edits)
        self._current_map = None

        self._build_ribbon()
        self._build_documents()
        self._build_explorer()
        self._build_properties()
        self._build_messages()
        self._build_status()
        self.log(f"LithoLog Studio {__version__} ready. Open borehole data (Home ▸ Open data) "
                 "or load the demo project.")

    # ------------------------------------------------------------------ layout
    def _build_ribbon(self):
        r = self.ribbon = Ribbon()
        home = r.page("Home")
        r.group(home, "Project file", [
            ("proj_open", "mdi6.folder-star-outline", "Open project", self.open_project, False),
            ("proj_save", "mdi6.content-save-outline", "Save project", self.save_project, False),
        ])
        r.group(home, "Data", [
            ("open", "mdi6.folder-open-outline", "Open data", self.open_data, False),
            ("legend", "mdi6.palette-outline", "Legend", self.open_legend, False),
            ("boundary", "mdi6.vector-polygon", "Boundary", self.open_boundary, False),
            ("dem", "mdi6.terrain", "DEM", self.open_dem, False),
            ("demo", "mdi6.flask-outline", "Demo project", self.open_demo, False),
        ])
        r.group(home, "Output", [
            ("shot", "mdi6.camera-outline", "Save image", self.save_image, False),
            ("pdf", "mdi6.file-pdf-box", "Save page", self.save_page, False),
        ])
        bh = r.page("Boreholes")
        r.group(bh, "Logs", [
            ("log", "mdi6.format-list-text", "Strip log", self.show_striplog, False),
            ("logs", "mdi6.file-multiple-outline", "All logs (PDF)", self.export_all_logs, False),
        ])
        r.group(bh, "Check", [("validate", "mdi6.check-decagram-outline", "Validate data", self.validate, False)])
        sec = r.page("Sections")
        r.group(sec, "Cross-section", [("section", "mdi6.chart-timeline-variant", "New section", self.new_section, False)])
        r.group(sec, "Fence", [
            ("fence", "mdi6.fence", "Fence diagram", self.show_fence, False),
        ])
        mp = r.page("Maps")
        r.group(mp, "Contour maps", [("map", "mdi6.map-outline", "New map", self.new_map, False)])
        r.group(mp, "Export", [("asc", "mdi6.grid", "Grid (.asc)", self.export_grid, False)])
        md = r.page("3D Model")
        r.group(md, "Model", [("build", "mdi6.cube-outline", "Build model", self.build_model, False)])
        r.group(md, "Layers", [("layers", "mdi6.palette-swatch-outline", "Layer\nproperties",
                                lambda: self.layer_properties(), False)])
        r.group(md, "Views", [
            ("v_iso", "mdi6.axis-arrow", "Oblique", lambda: self.view("iso_sw"), False),
            ("v_ne", "mdi6.rotate-3d-variant", "Oblique NE", lambda: self.view("iso_ne"), False),
            ("v_top", "mdi6.arrow-collapse-down", "Top", lambda: self.view("top"), False),
            ("v_front", "mdi6.arrow-up-bold-box-outline", "Front", lambda: self.view("front"), False),
            ("v_back", "mdi6.arrow-down-bold-box-outline", "Back", lambda: self.view("back"), False),
            ("v_left", "mdi6.arrow-right-bold-box-outline", "Left", lambda: self.view("left"), False),
            ("v_right", "mdi6.arrow-left-bold-box-outline", "Right", lambda: self.view("right"), False),
        ])
        r.group(md, "Tools", [
            ("clip", "mdi6.content-cut", "Cut plane", self.toggle_clip, True),
        ])
        r.group(md, "Export", [
            ("html", "mdi6.web", "3D web page", self.export_html, False),
            ("mesh", "mdi6.cube-send", "Solids (OBJ/STL)", self.export_meshes, False),
            ("vtk", "mdi6.database-export-outline", "ParaView", self.export_vtk, False),
            ("csv", "mdi6.table-arrow-right", "Volumes", self.export_volumes, False),
        ])
        an = r.page("Analysis")
        r.group(an, "Groundwater", [
            ("aquifer", "mdi6.water-outline", "Aquifer &\nstorage", self.aquifer, False),
        ])
        r.group(an, "3D properties", [
            ("prop", "mdi6.chart-bubble", "Property\nmodel", self.property_model, False),
        ])
        r.group(an, "Layers", [
            ("strat", "mdi6.layers-outline", "Stratigraphy\nmodel", self.strat_model, False),
        ])
        r.group(an, "Chemistry", [
            ("chem", "mdi6.flask-round-bottom-outline", "Hydro-\nchemistry", self.hydrochemistry, False),
        ])
        r.group(an, "Structure", [
            ("fract", "mdi6.compass-outline", "Fractures", self.show_fractures, False),
        ])
        vw = r.page("View")
        r.group(vw, "Theme", [
            ("th_dark", "mdi6.weather-night", "Dark", lambda: self.set_theme("dark"), True),
            ("th_light", "mdi6.white-balance-sunny", "Light", lambda: self.set_theme("light"), True),
        ])
        r.group(vw, "3D background", [
            ("bg_theme", "mdi6.gradient-vertical", "Theme", lambda: self.set_bg("theme"), True),
            ("bg_white", "mdi6.square-outline", "White", lambda: self.set_bg("white"), True),
            ("bg_sky", "mdi6.weather-partly-cloudy", "Sky", lambda: self.set_bg("sky"), True),
            ("bg_black", "mdi6.square", "Black", lambda: self.set_bg("black"), True),
        ])
        r.group(vw, "Show", [
            ("sh_legend", "mdi6.format-list-bulleted-type", "Legend bar", self.toggle_legend, True),
            ("sh_grid", "mdi6.axis-arrow-info", "Axes grid", self.toggle_grid, True),
            ("sh_terrain", "mdi6.terrain", "Terrain\n(DEM)", self.toggle_terrain, True),
        ])
        r.group(vw, "Rendering", [
            ("rn_grain", "mdi6.texture-box", "Rock\ntexture", lambda on: self.set_texture("grain", on), True),
            ("rn_pattern", "mdi6.view-grid-outline", "Pattern\ntexture", lambda on: self.set_texture("pattern", on),
             True),
            ("rn_vivid", "mdi6.palette", "Vivid\ncolour", lambda on: self.set_look("vivid", on), True),
            ("rn_edges", "mdi6.vector-polyline", "Contact\nlines", lambda on: self.set_look("edges", on), True),
            ("rn_ssao", "mdi6.brightness-6", "Ambient\nocclusion", lambda on: self.set_look("ssao", on), True),
        ])
        r.group(vw, "Layers", [("layers2", "mdi6.palette-swatch-outline", "Layer\nproperties",
                                lambda: self.layer_properties(), False)])
        r.buttons["sh_legend"].setChecked(True)
        r.buttons["sh_grid"].setChecked(True)
        r.buttons["bg_theme"].setChecked(True)
        from .viewer3d import DEFAULT_LOOK

        r.buttons["rn_grain"].setChecked(DEFAULT_LOOK["texture"] == "grain")
        r.buttons["rn_pattern"].setChecked(DEFAULT_LOOK["texture"] == "pattern")
        for k in ("vivid", "edges", "ssao"):
            r.buttons[f"rn_{k}"].setChecked(DEFAULT_LOOK[k])
        r.buttons["th_dark"].setChecked(theme.MODE == "dark")
        r.buttons["th_light"].setChecked(theme.MODE == "light")
        self.setMenuWidget(r)

    def _build_documents(self):
        self.docs = QTabWidget()
        self.docs.setObjectName("Documents")
        self.docs.setDocumentMode(True)
        self.viewer = Viewer3D()
        self.viewer.message.connect(self.log)
        self.viewer.legend.edit_requested.connect(self.layer_properties)
        self.viewer.legend.visibility_changed.connect(self._set_unit_visible)
        self.doc_log = FigureDoc("Select a borehole in the Project panel and click Boreholes ▸ Strip log.")
        self.doc_sec = FigureDoc("Sections ▸ New section to draw a cross-section.")
        self.doc_fence = FigureDoc("Sections ▸ Fence diagram.")
        self.doc_map = FigureDoc("Maps ▸ New map to draw a contour map.")
        self.doc_chem = ChemDoc()
        self.doc_fract = FigureDoc("Analysis ▸ Fractures (needs a Fractures sheet in the data).")
        for w, name, ic in [(self.viewer, "3D Model", "mdi6.cube-outline"),
                            (self.doc_log, "Strip Log", "mdi6.format-list-text"),
                            (self.doc_sec, "Cross-Section", "mdi6.chart-timeline-variant"),
                            (self.doc_fence, "Fence", "mdi6.fence"),
                            (self.doc_map, "Map", "mdi6.map-outline"),
                            (self.doc_chem, "Chemistry", "mdi6.flask-round-bottom-outline"),
                            (self.doc_fract, "Fractures", "mdi6.compass-outline")]:
            self.docs.addTab(w, theme.icon(ic, theme.TEXT_DIM), name)
            self._doc_icons = getattr(self, "_doc_icons", []) + [ic]
        self.setCentralWidget(self.docs)

    def _dock(self, title, widget, area):
        d = QDockWidget(title, self)
        d.setWidget(widget)
        d.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(area, d)
        return d

    def _build_explorer(self):
        t = self.tree = QTreeWidget()
        t.setHeaderHidden(True)
        t.setIndentation(14)
        t.itemChanged.connect(self._tree_changed)
        t.itemDoubleClicked.connect(self._tree_double)
        self._dock("Project", t, Qt.LeftDockWidgetArea).setMinimumWidth(270)
        self._refresh_tree()

    def _build_properties(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        g = QGroupBox("Model")
        f = QFormLayout(g)
        self.p_method = QComboBox()
        self.p_method.addItem("Horizons – correlated layers", "horizons")
        self.p_method.addItem("Voxel – indicator interpolation", "voxel")
        self.p_method.setToolTip("Horizons: every layer is traced from hole to hole and its thickness "
                                 "interpolated, so thin repeated layers (e.g. fracture zones) stay continuous, "
                                 "like GMS 'Horizons → Solids'.\nVoxel: each cell takes the lithology most "
                                 "boreholes have at that depth (good for irregular bodies/lenses).")
        self.p_grid = QComboBox()
        for label, val in [("Inverse distance", "idw"), ("Kriging", "kriging"), ("Linear (TIN)", "linear")]:
            self.p_grid.addItem(label, val)
        self.p_usedem = QCheckBox("Use DEM as ground surface")
        self.p_rectify = QCheckBox("Replace collar elevations with DEM")
        self.p_usedem.setEnabled(False)
        self.p_rectify.setEnabled(False)
        self.p_datum = QComboBox()
        self.p_datum.addItem("Depth below ground (hard rock)", "depth")
        self.p_datum.addItem("Elevation (layered sediments)", "elevation")
        self.p_cell = QDoubleSpinBox(maximum=1e5, singleStep=50, decimals=0, suffix=" m", specialValueText="Auto")
        self.p_dz = QDoubleSpinBox(maximum=1000, singleStep=0.5, decimals=1, suffix=" m", specialValueText="Auto")
        self.p_clipb = QCheckBox("Clip to study area")
        self.p_clipb.setChecked(True)
        self.p_smooth = QSlider(Qt.Horizontal, minimum=0, maximum=12, value=4)
        f.addRow("Method", self.p_method)
        f.addRow("Interpolation", self.p_grid)
        f.addRow("Correlate at", self.p_datum)
        f.addRow("Cell (XY)", self.p_cell)
        f.addRow("Cell (Z)", self.p_dz)
        f.addRow("Smoothing", self.p_smooth)
        f.addRow("", self.p_clipb)
        f.addRow("", self.p_usedem)
        f.addRow("", self.p_rectify)
        self.p_method.currentIndexChanged.connect(self._method_changed)
        self._method_changed()
        b = self.build_btn = QPushButton(theme.icon("mdi6.cube-outline", theme.ON_ACCENT), "  Build model")
        b.setObjectName("Primary")
        b.clicked.connect(self.build_model)
        f.addRow(b)
        v.addWidget(g)

        g = QGroupBox("Display")
        f = QFormLayout(g)
        self.p_ve = QDoubleSpinBox(minimum=0, maximum=1000, singleStep=5, decimals=0, specialValueText="Auto")
        self.p_opacity = QSlider(Qt.Horizontal, minimum=10, maximum=100, value=100)
        self.p_cut = QComboBox()
        for label, val in [("None", None), ("Remove SW quarter", "sw"), ("Remove SE quarter", "se"),
                           ("Remove NE quarter", "ne"), ("Remove NW quarter", "nw")]:
            self.p_cut.addItem(label, val)
        self.p_holes = QCheckBox("Boreholes")
        self.p_labels = QCheckBox("Labels")
        self.p_bnd = QCheckBox("Boundary")
        for c in (self.p_holes, self.p_labels, self.p_bnd):
            c.setChecked(True)
        f.addRow("Vertical exaggeration", self.p_ve)
        f.addRow("Opacity", self.p_opacity)
        f.addRow("Cut-away", self.p_cut)
        row = QHBoxLayout()
        for c in (self.p_holes, self.p_labels, self.p_bnd):
            row.addWidget(c)
        f.addRow(row)
        self.p_ve.editingFinished.connect(self.redraw)
        self.p_cut.currentIndexChanged.connect(self.redraw)
        self.p_smooth.sliderReleased.connect(self.redraw)
        for c in (self.p_holes, self.p_labels, self.p_bnd):
            c.toggled.connect(self.redraw)
        self.p_opacity.valueChanged.connect(lambda val: self.viewer.set_opacity(val / 100, self._unit_opacity()))
        v.addWidget(g)

        g = QGroupBox("Volumes && storage")
        gv = QVBoxLayout(g)
        self.vol = QTableWidget(0, 5)
        self.vol.setHorizontalHeaderLabels(["Unit", "Volume\n(MCM)", "%", "Specific\nyield", "Storage\n(MCM)"])
        self.vol.verticalHeader().setVisible(False)
        self.vol.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.vol.horizontalHeader().setMinimumSectionSize(40)
        self.vol.setWordWrap(False)
        for c in range(1, 5):
            self.vol.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.vol.setMinimumHeight(190)
        self.vol.itemChanged.connect(self._sy_changed)
        self.hvol = QTableWidget(0, 5)
        self.hvol.setHorizontalHeaderLabels(["Horizon (top → bottom)", "Holes", "Mean\nthick. (m)", "Area\n(%)",
                                             "Volume\n(MCM)"])
        self.hvol.verticalHeader().setVisible(False)
        self.hvol.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            self.hvol.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.hvol.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.vtabs = QTabWidget()
        self.vtabs.addTab(self.vol, "By layer")
        self.vtabs.addTab(self.hvol, "By horizon")
        self.vtabs.setMinimumHeight(230)
        gv.addWidget(self.vtabs)
        self.vol_note = QLabel("Build a model to see volumes. Type a specific yield to estimate storage.")
        self.vol_note.setObjectName("Dim")
        self.vol_note.setWordWrap(True)
        gv.addWidget(self.vol_note)
        v.addWidget(g)
        v.addStretch(1)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(w)
        self._dock("Properties", sc, Qt.RightDockWidgetArea).setMinimumWidth(410)

    def _build_messages(self):
        self.msgs = QPlainTextEdit(readOnly=True)
        self.msgs.setMaximumBlockCount(2000)
        d = self._dock("Messages", self.msgs, Qt.BottomDockWidgetArea)
        d.setMaximumHeight(150)

    def _build_status(self):
        sb = self.statusBar()
        self.busy = QProgressBar()
        self.busy.setMaximumWidth(180)
        self.busy.setRange(0, 0)
        self.busy.hide()
        self.status = QLabel("Ready")
        sb.addWidget(self.status, 1)
        sb.addPermanentWidget(self.busy)
        sb.addPermanentWidget(QLabel(f"  LithoLog {__version__} · open source (MIT)  "))

    # ------------------------------------------------------------------ helpers
    def log(self, text: str):
        self.msgs.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {text}")
        self.status.setText(text.splitlines()[0][:160])

    def run(self, label, fn, done, *args, **kw):
        self.busy.show()
        self.log(label + " …")
        job = Job(fn, *args, **kw)

        def ok(result):
            self.busy.hide()
            done(result)

        def bad(msg):
            self.busy.hide()
            self.log("Error: " + msg.splitlines()[0])
            QMessageBox.warning(self, "LithoLog Studio", msg.split("\n\n")[0])

        job.signals.done.connect(ok)
        job.signals.failed.connect(bad)
        self._job = job  # keep a reference while it runs
        self.pool.start(job)

    def need_project(self) -> bool:
        if self.project is None:
            QMessageBox.information(self, "LithoLog Studio", "Open borehole data first (Home ▸ Open data).")
            return False
        return True

    def _title(self):
        return self.project.name if self.project else ""

    # ------------------------------------------------------------------ project
    def open_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open borehole data", "", "Borehole data (*.xlsx *.xls *.txt *.dat *.tsv *.csv);;All files (*)")
        if path:
            self.load(path)

    def open_demo(self):
        self.load(str(DEMO), name="Demo project (synthetic)")

    def load(self, path, legend=None, name=None, boundary=None, after=None):
        from ..io import load_project

        def done(project):
            if name:
                project.name = name
            self.project, self.data_path, self.model, self.solids = project, path, None, None
            if not after:  # new data (not a project file): start with a clean layer set-up
                self.dem, self.dem_path, self.layer_state, self._legend_rows = None, None, {}, {}
                self.p_usedem.setEnabled(False)
                self.p_rectify.setEnabled(False)
            self.legend_path = legend
            self.boundary, self.boundary_path = None, None
            if boundary:
                from ..boundary import load_boundary

                b = project.boreholes.dropna(subset=["x", "y"])
                try:
                    self.boundary = load_boundary(boundary, near=(b["x"].min(), b["x"].max(),
                                                                  b["y"].min(), b["y"].max()))
                    self.boundary_path = boundary
                except Exception as e:  # noqa: BLE001
                    self.log(f"Boundary not loaded: {e}")
            if after:
                after()
            self._refresh_tree()
            self.viewer.clear()
            self.log(f"Loaded {Path(path).name}: {len(project.ids)} boreholes, "
                     f"{len(project.lithology)} intervals, {project.lithology['code'].nunique()} lithology codes.")
            self.validate(quiet=True)
            self.build_model()

        self.run(f"Reading {Path(path).name}", load_project, done, path, legend=legend)

    # ------------------------------------------------------------------ project files
    def settings(self) -> dict:
        return {"datum": self.p_datum.currentData(), "cell": self.p_cell.value(), "dz": self.p_dz.value(),
                "smooth": self.p_smooth.value(), "clip_boundary": self.p_clipb.isChecked(),
                "ve": self.p_ve.value(), "opacity": self.p_opacity.value(), "cutaway": self.p_cut.currentData(),
                "boreholes": self.p_holes.isChecked(), "labels": self.p_labels.isChecked(),
                "boundary": self.p_bnd.isChecked(), "specific_yield": self._sy(),
                "method": self.p_method.currentData(), "interpolation": self.p_grid.currentData(),
                "use_dem": self.p_usedem.isChecked(), "rectify": self.p_rectify.isChecked(),
                "layers": self.layer_state, "legend_rows": list(getattr(self, "_legend_rows", {}).values()),
                "legend_title": self.viewer.legend.title, "background": self.viewer.background,
                "look": self.viewer.look, "horizons_visible": {str(k): v for k, v in self.hz_state.items()}}

    def apply_settings(self, st: dict):
        for w in (self.p_datum, self.p_cut, self.p_cell, self.p_dz, self.p_smooth, self.p_ve, self.p_opacity,
                  self.p_holes, self.p_labels, self.p_bnd, self.p_clipb):
            w.blockSignals(True)
        self.p_datum.setCurrentIndex(max(0, self.p_datum.findData(st.get("datum", "depth"))))
        self.p_cut.setCurrentIndex(max(0, self.p_cut.findData(st.get("cutaway"))))
        self.p_cell.setValue(st.get("cell", 0))
        self.p_dz.setValue(st.get("dz", 0))
        self.p_smooth.setValue(st.get("smooth", 4))
        self.p_ve.setValue(st.get("ve", 0))
        self.p_opacity.setValue(st.get("opacity", 100))
        self.p_holes.setChecked(st.get("boreholes", True))
        self.p_labels.setChecked(st.get("labels", True))
        self.p_bnd.setChecked(st.get("boundary", True))
        self.p_clipb.setChecked(st.get("clip_boundary", True))
        self.p_method.setCurrentIndex(max(0, self.p_method.findData(st.get("method", "horizons"))))
        self.p_grid.setCurrentIndex(max(0, self.p_grid.findData(st.get("interpolation", "idw"))))
        self.p_usedem.setChecked(st.get("use_dem", True))
        self.p_rectify.setChecked(st.get("rectify", False))
        self.layer_state = {k: dict(v) for k, v in st.get("layers", {}).items()}
        self._legend_rows = {r["code"]: r for r in st.get("legend_rows", [])}
        self.viewer.legend.title = st.get("legend_title", "Lithology")
        if st.get("background"):
            self.set_bg(st["background"])
        if st.get("look"):
            self.viewer.look.update(st["look"])
            lk = self.viewer.look
            self.ribbon.buttons["rn_grain"].setChecked(lk.get("texture") == "grain")
            self.ribbon.buttons["rn_pattern"].setChecked(lk.get("texture") == "pattern")
            for k in ("vivid", "edges", "ssao"):
                self.ribbon.buttons[f"rn_{k}"].setChecked(bool(lk.get(k)))
        self._pending_hz = {int(k): v for k, v in st.get("horizons_visible", {}).items()}
        for w in (self.p_datum, self.p_cut, self.p_cell, self.p_dz, self.p_smooth, self.p_ve, self.p_opacity,
                  self.p_holes, self.p_labels, self.p_bnd, self.p_clipb):
            w.blockSignals(False)
        self._pending_sy = st.get("specific_yield", {})

    def save_project(self):
        if not self.need_project():
            return
        from .projectfile import save

        path, _ = QFileDialog.getSaveFileName(self, "Save project", f"{self.project.name}.llproj",
                                              "LithoLog project (*.llproj)")
        if path:
            save(path, self.project.name, self.data_path, self.legend_path, self.boundary_path, self.settings(),
                 dem=self.dem_path)
            self.log(f"Project saved: {path}")

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "LithoLog project (*.llproj)")
        if path:
            self.load_project_file(path)

    def load_project_file(self, path):
        from .projectfile import load

        try:
            pf = load(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Open project", str(e))
            return
        self.apply_settings(pf["settings"])
        dem = pf.get("dem")
        rows = list(getattr(self, "_legend_rows", {}).values())

        def after():
            if rows:
                self.project.legend = self.project.legend.updated(rows)
            if dem and Path(dem).exists():
                self._load_dem(dem)

        self.load(pf["data"], legend=pf.get("legend"), name=pf.get("name"), boundary=pf.get("boundary"),
                  after=after)

    def open_legend(self):
        if not self.need_project():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open legend", "", "Legend (*.csv *.xlsx)")
        if path:
            from ..io import load_legend

            self.project.legend = load_legend(path, self.project.legend)
            self.legend_path = path
            self._refresh_tree()
            self.log(f"Legend {Path(path).name} applied.")
            self.redraw()

    def open_boundary(self):
        if not self.need_project():
            return
        from ..boundary import BOUNDARY_TYPES

        path, _ = QFileDialog.getOpenFileName(self, "Open study-area boundary", "",
                                              BOUNDARY_TYPES + ";;Shapefile (*.shp);;Google Earth (*.kml *.kmz);;"
                                              "GeoJSON (*.geojson *.json);;All files (*)")
        if not path:
            return
        from ..boundary import load_boundary

        b = self.project.boreholes.dropna(subset=["x", "y"])
        near = (b["x"].min(), b["x"].max(), b["y"].min(), b["y"].max())
        try:
            self.boundary = load_boundary(path, near=near)
            self.boundary_path = path
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Boundary", str(e))
            return
        self.log(f"Boundary {Path(path).name}: {self.boundary.area / 1e6:,.1f} km². {self.boundary.crs_note}")
        self._refresh_tree()
        self.build_model()

    def validate(self, quiet=False):
        if not self.need_project():
            return
        from ..validate import validate

        issues = validate(self.project)
        n_err = sum(i.level == "error" for i in issues)
        self.log(f"Data check: {n_err} error(s), {len(issues) - n_err} warning(s).")
        for i in issues[:50]:
            self.log(f"  {i.level}: {i.borehole}: {i.message}")
        if not quiet and not issues:
            QMessageBox.information(self, "Data check", "No problems found.")

    # ------------------------------------------------------------------ explorer
    def _refresh_tree(self):
        t = self.tree
        t.blockSignals(True)
        t.clear()
        if self.project is None:
            QTreeWidgetItem(t, ["No project open"])
            t.blockSignals(False)
            return
        root = QTreeWidgetItem(t, [self.project.name])
        root.setIcon(0, theme.icon("mdi6.briefcase-outline", theme.ACCENT))
        bh = QTreeWidgetItem(root, [f"Boreholes ({len(self.project.ids)})"])
        bh.setIcon(0, theme.icon("mdi6.format-list-bulleted", theme.TEXT_DIM))
        for bid in self.project.ids:
            it = QTreeWidgetItem(bh, [bid])
            it.setIcon(0, theme.icon("mdi6.circle-medium", theme.ACCENT_2))
            it.setData(0, Qt.UserRole, ("borehole", bid))
        lg = QTreeWidgetItem(root, ["Lithology legend"])
        lg.setIcon(0, theme.icon("mdi6.palette-outline", theme.TEXT_DIM))
        used = list(dict.fromkeys(c for c in self.project.lithology["code"] if c))
        for c in used:
            lt = self.project.legend.get(c)
            it = QTreeWidgetItem(lg, [f"{lt.name}  ({c})"])
            it.setIcon(0, swatch(lt.color))
            it.setData(0, Qt.UserRole, ("legend", c))
            it.setToolTip(0, "Double-click to edit colour, name and pattern")
        if self.boundary is not None:
            it = QTreeWidgetItem(root, [f"Study area · {self.boundary.area / 1e6:,.1f} km²"])
            it.setIcon(0, theme.icon("mdi6.vector-polygon", "#E0524F"))
        if self.dem is not None:
            z = self.dem.z
            import numpy as np

            it = QTreeWidgetItem(root, [f"DEM {self.dem.name} · {np.nanmin(z):.0f}–{np.nanmax(z):.0f} m"])
            it.setIcon(0, theme.icon("mdi6.terrain", "#6AAF6A"))
        if self.model is not None:
            mu = QTreeWidgetItem(root, ["3D model units"])
            mu.setIcon(0, theme.icon("mdi6.cube-outline", theme.TEXT_DIM))
            mu.setFlags(mu.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            mu.setToolTip(0, "Tick / untick to show or hide all layers")
            for c in self.model.codes:
                it = QTreeWidgetItem(mu, [self.project.legend.get(c).name])
                it.setIcon(0, swatch(self.project.legend.get(c).color))
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                vis = self.layer_state.get(c, {}).get("visible", True)
                it.setCheckState(0, Qt.Checked if vis else Qt.Unchecked)
                it.setData(0, Qt.UserRole, ("unit", c))
                it.setToolTip(0, "Tick to show/hide · double-click for layer properties")
            if getattr(self.model, "kind", "") == "horizon":
                hz = QTreeWidgetItem(root, [f"Horizons ({len(self.model.horizons)})"])
                hz.setIcon(0, theme.icon("mdi6.layers-triple-outline", theme.TEXT_DIM))
                hz.setFlags(hz.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                hz.setToolTip(0, "Tick / untick each horizon to show or hide it in 3D")
                for k, (lab, h, v) in enumerate(zip(self.model.h_labels, self.model.horizons,
                                                    self.model.h_volumes)):
                    it = QTreeWidgetItem(hz, [f"{k + 1}. {lab} · {v / 1e6:,.1f} MCM"])
                    it.setIcon(0, swatch(self.project.legend.get(h["code"]).color))
                    it.setData(0, Qt.UserRole, ("horizon", k, h["code"]))
                    it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                    it.setCheckState(0, Qt.Checked if self.hz_state.get(k, True) else Qt.Unchecked)
                    it.setToolTip(0, f"Present in {h['n']} boreholes · tick to show/hide · "
                                     "double-click for layer properties")
                hz.setExpanded(True)
                _sync_parent(hz)
        if self.model is not None:
            _sync_parent(mu)
        t.expandAll()
        bh.setExpanded(len(self.project.ids) <= 30)
        t.blockSignals(False)

    def _tree_changed(self, item, col):
        tag = item.data(0, Qt.UserRole)
        if tag and tag[0] == "horizon":
            vis = item.checkState(0) == Qt.Checked
            self.hz_state[tag[1]] = vis
            self.viewer.set_horizon_visible(tag[1], vis)
            return
        if tag and tag[0] == "unit":
            vis = item.checkState(0) == Qt.Checked
            self.layer_state.setdefault(tag[1], {})["visible"] = vis
            self.viewer.set_unit_visible(tag[1], vis)
            self.viewer.legend.set_visible_code(tag[1], vis)

    def _tree_double(self, item, col):
        tag = item.data(0, Qt.UserRole)
        if tag and tag[0] == "borehole":
            self.show_striplog(bid=tag[1])
        elif tag and tag[0] in ("unit", "legend"):
            self.layer_properties(tag[1])
        elif tag and tag[0] == "horizon":
            self.layer_properties(tag[2])

    def _set_unit_visible(self, code, vis):
        """From the legend bar: keep explorer, viewer and state in step."""
        self.layer_state.setdefault(code, {})["visible"] = vis
        self.viewer.set_unit_visible(code, vis)
        root = self.tree.invisibleRootItem()
        stack = [root]
        self.tree.blockSignals(True)
        while stack:
            it = stack.pop()
            for k in range(it.childCount()):
                stack.append(it.child(k))
            tag = it.data(0, Qt.UserRole) if it is not root else None
            if tag == ("unit", code):
                it.setCheckState(0, Qt.Checked if vis else Qt.Unchecked)
        self.tree.blockSignals(False)

    def _unit_opacity(self):
        return {c: st.get("opacity", 1.0) for c, st in self.layer_state.items()}

    def _selected_borehole(self):
        it = self.tree.currentItem()
        tag = it.data(0, Qt.UserRole) if it else None
        if tag and tag[0] == "borehole":
            return tag[1]
        return self.project.ids[0] if self.project and self.project.ids else None

    # ------------------------------------------------------------------ 3D model
    def _method_changed(self, *_):
        horizons = self.p_method.currentData() == "horizons"
        self.p_datum.setEnabled(not horizons)
        self.p_grid.setEnabled(horizons)
        self.p_smooth.setEnabled(not horizons)

    def _build(self, project, method, cell, dz, datum, grid, boundary, dem, rectify):
        """Runs on the worker thread."""
        if dem is not None:
            from ..dem import rectify_collars

            rep = rectify_collars(project, dem, replace=rectify)
            d = rep["difference"].dropna()
            self._dem_report = (len(d), float(d.mean()) if len(d) else 0.0,
                                float(d.abs().max()) if len(d) else 0.0)
        if method == "horizons":
            from ..horizons import build_horizon_model

            return build_horizon_model(project, cell, dz, method=grid, boundary=boundary, dem=dem)
        from ..model3d import build_model

        return build_model(project, cell, dz, datum=datum, boundary=boundary, dem=dem)

    def build_model(self):
        if not self.need_project():
            return
        cell = self.p_cell.value() or None
        dz = self.p_dz.value() or None
        b = self.boundary if self.p_clipb.isChecked() else None
        dem = self.dem if (self.dem is not None and self.p_usedem.isChecked()) else None
        self._dem_report = None

        def done(model):
            self.model = model
            self.hz_state = getattr(self, "_pending_hz", None) or {}
            self._pending_hz = None
            self._refresh_tree()
            nz, ny, nx = model.lith.shape
            kind = "Horizon model" if getattr(model, "kind", "") == "horizon" else "Voxel model"
            self.log(f"{kind} built: {nx} × {ny} × {nz} cells ({model.cell:g} × {model.cell:g} × {model.dz:g} m)"
                     + (f"; clipped to study area, {100 * (1 - model.coverage):.0f} % beyond borehole cover"
                        if model.coverage is not None else ""))
            if getattr(model, "kind", "") == "horizon":
                self.log(f"  {len(model.horizons)} horizons traced between the boreholes: "
                         + "; ".join(model.h_labels))
                if model.h_note:
                    self.log("  Note: " + model.h_note)
            if self._dem_report:
                n, mean, mx = self._dem_report
                self.log(f"  DEM: collar − DEM difference mean {mean:+.1f} m, max {mx:.1f} m over {n} holes"
                         + (" (collars replaced by the DEM)" if self.p_rectify.isChecked() else ""))
            self.redraw(reset_view=True)
            self._fill_volumes(getattr(self, "_pending_sy", None) or None)
            self._pending_sy = None
            self.docs.setCurrentWidget(self.viewer)

        self.run("Building 3D model", self._build, done, self.project, self.p_method.currentData(), cell, dz,
                 self.p_datum.currentData(), self.p_grid.currentData(), b, dem, self.p_rectify.isChecked())

    def _auto_ve(self):
        m = self.model
        xr, yr = m.x[-1] - m.x[0], m.y[-1] - m.y[0]
        zr = (m.z[-1] - m.z[0]) or 1
        return float(max(1, round(0.3 * max(xr, yr) / zr)))

    def redraw(self, reset_view=False):
        if self.model is None:
            return
        from ..solid import build_solids

        cut = self.p_cut.currentData()
        self.solids = build_solids(self.model, self.p_smooth.value() / 4, cut,
                                   per_horizon=getattr(self.model, "kind", "") == "horizon")
        ve = self.p_ve.value() or self._auto_ve()
        cam = None if reset_view else self.viewer.plotter.camera_position
        self.viewer.show_model(self.model, self.solids, self.project.legend, ve,
                               boreholes=self.p_holes.isChecked(), labels=self.p_labels.isChecked(),
                               boundary=self.p_bnd.isChecked(), opacity=self.p_opacity.value() / 100,
                               cutaway=cut)
        if cam is not None and not reset_view:
            self.viewer.plotter.camera_position = cam
        # keep unit visibility in sync with the explorer check boxes
        root = self.tree.invisibleRootItem()
        stack = [root]
        while stack:
            it = stack.pop()
            for k in range(it.childCount()):
                stack.append(it.child(k))
            tag = it.data(0, Qt.UserRole) if it is not root else None
            if tag and tag[0] == "unit" and it.checkState(0) != Qt.Checked:
                self.viewer.set_unit_visible(tag[1], False)
        self.viewer.code_vis = {c: st.get("visible", True) for c, st in self.layer_state.items()}
        self.viewer.hz_vis = dict(self.hz_state)
        self.viewer._apply_visibility(render=False)
        if self.viewer.look.get("ssao"):
            self.viewer.set_ssao(True)
        self.viewer.set_opacity(self.p_opacity.value() / 100, self._unit_opacity())
        if self.ribbon.buttons["sh_terrain"].isChecked() and self.dem is not None:
            self.viewer.show_terrain(self.dem, self.model, ve)
        self._update_legend()
        self.viewer.plotter.render()
        self.ribbon.buttons["clip"].setChecked(False)

    def view(self, name):
        self.docs.setCurrentWidget(self.viewer)
        self.viewer.set_view(name)

    def toggle_clip(self, on):
        if self.model is None:
            self.ribbon.buttons["clip"].setChecked(False)
            return
        self.docs.setCurrentWidget(self.viewer)
        self.viewer.enable_clip() if on else self.viewer.disable_clip()

    def _sy(self):
        sy = {}
        for r in range(self.vol.rowCount()):
            code = self.vol.item(r, 0).data(Qt.UserRole) if self.vol.item(r, 0) else None
            it = self.vol.item(r, 3)
            if code and it:
                try:
                    v = float(it.text() or 0)
                except ValueError:
                    v = 0
                if v > 0:
                    sy[code] = v
        return sy

    def _fill_volumes(self, sy=None):
        m = self.model
        vols = m.volumes(sy or {})
        self.vol.blockSignals(True)
        self.vol.setRowCount(len(vols) + 1)
        tot_v = tot_s = 0.0
        for r, (_, row) in enumerate(vols.iterrows()):
            lt = self.project.legend.get(row["code"])
            name = QTableWidgetItem(swatch(lt.color), lt.name)
            name.setData(Qt.UserRole, row["code"])
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)
            self.vol.setItem(r, 0, name)
            for c, val in ((1, f"{row['volume_mcm']:,.1f}"), (2, f"{row['percent']:.1f}")):
                it = QTableWidgetItem(val)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.vol.setItem(r, c, it)
            s = row.get("specific_yield") if "specific_yield" in row else None
            it = QTableWidgetItem("" if s is None or s != s else f"{s:g}")
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it.setToolTip("Type a specific yield (e.g. 0.015) to estimate storage")
            self.vol.setItem(r, 3, it)
            st = row.get("storage_mcm") if "storage_mcm" in row else None
            it = QTableWidgetItem("" if st is None or st != st else f"{st:,.2f}")
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it.setForeground(QColor(theme.ACCENT))
            self.vol.setItem(r, 4, it)
            tot_v += row["volume_mcm"]
            tot_s += 0 if st is None or st != st else st
        r = len(vols)
        for c, val in ((0, "Total"), (1, f"{tot_v:,.1f}"), (2, "100.0"), (3, ""),
                       (4, f"{tot_s:,.2f}" if tot_s else "")):
            it = QTableWidgetItem(val)
            it.setFlags(Qt.ItemIsEnabled)
            f = it.font()
            f.setBold(True)
            it.setFont(f)
            if c:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.vol.setItem(r, c, it)
        self.vol.blockSignals(False)
        self._fill_horizons()
        self._update_legend()
        note = "MCM = million m³, ground to base of drilling"
        if m.boundary is not None:
            note += f", inside the study area ({m.boundary.area / 1e6:,.1f} km²)"
        self.vol_note.setText(note + ". Storage = volume × specific yield (your estimate).")

    def _sy_changed(self, item):
        if item.column() == 3 and self.model is not None:
            self._fill_volumes(self._sy())

    def _fill_horizons(self):
        m = self.model
        horizons = getattr(m, "kind", "") == "horizon"
        self.vtabs.setTabEnabled(1, horizons)
        if not horizons:
            self.hvol.setRowCount(0)
            return
        from ..horizons import horizon_volumes

        hv = horizon_volumes(m)
        self.hvol.setRowCount(len(hv))
        for r, (_, row) in enumerate(hv.iterrows()):
            lt = self.project.legend.get(row["code"])
            it = QTableWidgetItem(swatch(lt.color), f"{row['horizon']}. {row['layer']}")
            self.hvol.setItem(r, 0, it)
            for c, val in ((1, f"{row['holes_present']}"), (2, f"{row['mean_thickness_m']:.1f}"),
                           (3, f"{row['area_present_pct']:.0f}"), (4, f"{row['volume_mcm']:,.1f}")):
                it = QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.hvol.setItem(r, c, it)

    def _update_legend(self):
        if self.model is None or self.project is None:
            self.viewer.legend.set_items([])
            return
        vols = self.model.volumes()
        vol = dict(zip(vols["code"], vols["volume_mcm"]))
        shown = [s.code for s in (self.solids or [])] or list(self.model.codes)
        items = [dict(code=c, name=self.project.legend.get(c).name, color=self.project.legend.get(c).color,
                      volume=vol.get(c), visible=self.layer_state.get(c, {}).get("visible", True))
                 for c in self.model.codes if c in shown]
        sub = "Volumes in MCM (million m³), ground to base of drilling"
        if self.model.boundary is not None:
            sub += f", within the study area ({self.model.boundary.area / 1e6:,.1f} km²)"
        if getattr(self.model, "kind", "") == "horizon":
            sub += f" · {len(self.model.horizons)} correlated horizons"
        self.viewer.legend.set_items(items, sub)

    def layer_properties(self, code=None):
        if not self.need_project():
            return
        from .legendbar import LayerPropertiesDialog

        codes = list(self.model.codes) if self.model is not None else \
            list(dict.fromkeys(c for c in self.project.lithology["code"] if c))
        vols = {}
        if self.model is not None:
            v = self.model.volumes()
            vols = dict(zip(v["code"], v["volume_mcm"]))
        dlg = LayerPropertiesDialog(self.project.legend, codes, self.layer_state, code, vols, self)

        def apply():
            self.project.legend = self.project.legend.updated(dlg.rows())
            self._legend_rows = {r["code"]: r for r in dlg.rows()}
            for c, e in dlg.edits.items():
                self.layer_state[c] = {"visible": e["visible"], "opacity": e["opacity"]}
                self.viewer.set_unit_color(c, e["color"])
                self.viewer.set_unit_visible(c, e["visible"])
            self.viewer.set_opacity(self.p_opacity.value() / 100, self._unit_opacity())
            self._refresh_tree()
            if self.model is not None:
                self._fill_volumes(self._sy())
                if self.viewer.look.get("texture", "none") != "none" or self.viewer.look.get("edges"):
                    self.redraw()
            for fn in list(self._redo.values()):  # redraw open logs, sections, maps with the new legend
                try:
                    fn()
                except Exception as e:  # noqa: BLE001
                    self.log(f"Could not redraw: {e}")
            self.viewer.plotter.render()
            self.log("Layer properties applied.")

        dlg.apply_btn.clicked.connect(apply)
        if dlg.exec() == QDialog.Accepted:
            apply()

    def open_dem(self):
        if not self.need_project():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open DEM", "",
                                              "DEM (*.tif *.tiff *.asc);;GeoTIFF (*.tif *.tiff);;ESRI ASCII (*.asc)")
        if path:
            self._load_dem(path, rebuild=True)

    def _load_dem(self, path, rebuild=False):
        import numpy as np

        from ..dem import load_dem, sample

        try:
            dem = load_dem(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "DEM", str(e))
            return
        b = self.project.boreholes.dropna(subset=["x", "y"])
        crs = None
        if dem.crs is not None and dem.crs.is_geographic and len(b):
            from ..aquifer import utm_epsg
            from ..dem import MODEL_CRS

            lon = dem.x0 + dem.z.shape[1] * dem.dx / 2
            lat = dem.y0 - dem.z.shape[0] * dem.dy / 2
            crs = MODEL_CRS["crs"] = f"EPSG:{utm_epsg(lon, lat)}"
        z = sample(dem, b["x"], b["y"], crs) if len(b) else np.array([])
        n_in = int(np.isfinite(z).sum())
        if len(b) and n_in == 0:
            QMessageBox.warning(self, "DEM", "The DEM does not cover the boreholes. Check that it is in the "
                                             "boreholes' coordinate system or in latitude/longitude.")
            return
        self.dem, self.dem_path = dem, path
        self.p_usedem.setEnabled(True)
        self.p_rectify.setEnabled(True)
        if rebuild:
            self.p_usedem.setChecked(True)
        d = (b["elevation"].to_numpy(float) - z)[np.isfinite(z)]
        self.log(f"DEM {Path(path).name}: {dem.z.shape[1]} × {dem.z.shape[0]} cells, "
                 f"{np.nanmin(dem.z):.0f}–{np.nanmax(dem.z):.0f} m; covers {n_in} of {len(b)} boreholes"
                 + (f"; collar − DEM mean {np.nanmean(d):+.1f} m, max |{np.nanmax(np.abs(d)):.1f}| m"
                    if np.isfinite(d).any() else ""))
        self._refresh_tree()
        if rebuild:
            self.ribbon.buttons["sh_terrain"].setChecked(True)
            self.build_model()

    # ------------------------------------------------------------------ view
    def set_theme(self, mode):
        from PySide6.QtWidgets import QApplication

        theme.apply(QApplication.instance(), mode)
        theme.save_mode(mode)
        self.ribbon.buttons["th_dark"].setChecked(mode == "dark")
        self.ribbon.buttons["th_light"].setChecked(mode == "light")
        self.ribbon.refresh_icons()
        for k, ic in enumerate(getattr(self, "_doc_icons", [])):
            self.docs.setTabIcon(k, theme.icon(ic, theme.TEXT_DIM))
        for d in (self.doc_log, self.doc_sec, self.doc_fence, self.doc_map, self.doc_fract):
            d.apply_theme()
        self.build_btn.setIcon(theme.icon("mdi6.cube-outline", theme.ON_ACCENT))
        self.viewer.apply_theme()
        self._refresh_tree()
        if self.model is not None:
            self._fill_volumes(self._sy())
            self.redraw()

    def set_texture(self, kind, on):
        self.ribbon.buttons["rn_grain"].setChecked(on and kind == "grain")
        self.ribbon.buttons["rn_pattern"].setChecked(on and kind == "pattern")
        self.viewer.look["texture"] = kind if on else "none"
        self.redraw()

    def set_look(self, key, on):
        self.viewer.look[key] = bool(on)
        if key == "ssao":
            self.viewer.set_ssao(on)
        else:
            self.redraw()

    def set_bg(self, name):
        for k in ("theme", "white", "sky", "black"):
            self.ribbon.buttons[f"bg_{k}"].setChecked(k == name)
        self.viewer.set_background(name)
        if self.model is not None:
            self.redraw()

    def toggle_legend(self, on):
        self.viewer.legend.set_enabled_bar(on)

    def toggle_grid(self, on):
        self.viewer.set_axes_grid(on)

    def toggle_terrain(self, on):
        if self.model is None:
            return
        if on and self.dem is None:
            self.ribbon.buttons["sh_terrain"].setChecked(False)
            QMessageBox.information(self, "Terrain", "Load a DEM first (Home ▸ DEM).")
            return
        if on:
            self.viewer.show_terrain(self.dem, self.model, self.viewer.ve)
        else:
            self.viewer.remove("terrain")
            try:
                self.viewer.plotter.remove_scalar_bar("DEM elevation (m)")
            except Exception:  # noqa: BLE001
                pass
            self.viewer.plotter.render()

    # ------------------------------------------------------------------ 2D documents
    def show_striplog(self, checked=False, bid=None):
        if not self.need_project():
            return
        from ..striplog import Style, striplog_pages

        bid = bid or self._selected_borehole()

        def make():
            return next(iter(striplog_pages(self.project.borehole(bid), self.project.legend,
                                            Style(project_name=self._title()))))

        self.doc_log.set_figure(make())
        self._redo[self.doc_log] = lambda: self.doc_log.set_figure(make())
        self.docs.setCurrentWidget(self.doc_log)
        self.log(f"Strip log {bid}.")

    def export_all_logs(self):
        if not self.need_project():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save all strip logs", "strip_logs.pdf", "PDF (*.pdf)")
        if not path:
            return
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages

        from ..striplog import Style, striplog_pages

        def work():
            with PdfPages(path) as pdf:
                for bid in self.project.ids:
                    for fig in striplog_pages(self.project.borehole(bid), self.project.legend,
                                              Style(project_name=self._title())):
                        pdf.savefig(fig)
                        plt.close(fig)
            return path

        self.run("Writing all strip logs", work, lambda p: self.log(f"Saved {p}"))

    def new_section(self):
        if not self.need_project():
            return
        dlg = SectionDialog(self.project, self)
        if dlg.exec() != QDialog.Accepted:
            return
        ids, name, ve, datum, style, curve = dlg.values()
        from ..section import section_figure, through_boreholes

        try:
            line = through_boreholes(self.project, ids, name)

            def make():
                return section_figure(self.project, line, legend=self.project.legend, ve=ve or None,
                                      title=self._title(), datum=datum, style=style, curve=curve)

            fig = make()
        except ValueError as e:
            QMessageBox.warning(self, "Section", str(e))
            return
        self.doc_sec.set_figure(fig)
        self._redo[self.doc_sec] = lambda: self.doc_sec.set_figure(make())
        self.docs.setCurrentWidget(self.doc_sec)
        self.log(f"Section {name}: {len(ids)} boreholes, {line.length:,.0f} m.")

    def show_fence(self):
        if not self.need_project():
            return
        from ..fence import fence_figure, network_edges

        edges = network_edges(self.project, None, "mst")
        fig = fence_figure(self.project, edges, title=self._title())
        self.doc_fence.set_figure(fig)
        self._redo[self.doc_fence] = lambda: self.doc_fence.set_figure(
            fence_figure(self.project, edges, title=self._title()))
        self.docs.setCurrentWidget(self.doc_fence)
        self.log(f"Fence diagram: {len(edges)} panels.")

    def new_map(self):
        if not self.need_project():
            return
        dlg = MapDialog(self.project, self.boundary is not None, self)
        if dlg.exec() != QDialog.Accepted:
            return
        attr, method, cell, clip = dlg.values()
        from ..grid import grid_attribute
        from ..maps import map_figure

        try:
            g, vals = grid_attribute(self.project, attr, method, cell or None,
                                     boundary=self.boundary if clip else None)
        except ValueError as e:
            QMessageBox.warning(self, "Map", str(e))
            return
        def make():
            return map_figure(g, vals, attr, legend=self.project.legend, method=method, title=self._title(),
                              all_xy=self.project.boreholes)

        self._current_map = g
        self.doc_map.set_figure(make())
        self._redo[self.doc_map] = lambda: self.doc_map.set_figure(make())
        self.docs.setCurrentWidget(self.doc_map)
        self.log(f"Map {attr} ({method}).")

    # ------------------------------------------------------------------ analysis
    def aquifer(self):
        if not self._need_model():
            return
        from ..aquifer import load_wells, saturated_volumes, water_table, wells_from_project

        path, _ = QFileDialog.getOpenFileName(
            self, "Observation wells (Cancel = use water levels in the borehole data)", "",
            "Wells (*.xlsx *.xls *.csv *.txt)")
        try:
            wells = load_wells(path) if path else wells_from_project(self.project)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Aquifer", str(e))
            return
        if wells is None:
            QMessageBox.information(self, "Aquifer", "No water levels: choose a wells file or fill the "
                                                     "WaterLevels sheet.")
            return
        reading = wells.readings[-1]
        if len(wells.readings) > 1:
            from PySide6.QtWidgets import QInputDialog

            reading, ok = QInputDialog.getItem(self, "Aquifer", "Water-level reading / season:",
                                               [str(r) for r in wells.readings], len(wells.readings) - 1, False)
            if not ok:
                return
        try:
            wt = water_table(self.model, wells, reading)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Aquifer", str(e))
            return
        self.water_table = wt
        sy = self._sy()
        v = saturated_volumes(self.model, wt, sy)
        from ..maps import map_figure

        vals = wt.wells.rename(columns={"well_id": "borehole_id"})
        fig = map_figure(wt.grid, vals.assign(value=vals["wt"]), "water", title=f"{self._title()} · {reading}")
        self.doc_map.set_figure(fig)
        self._redo.pop(self.doc_map, None)
        self.viewer.show_surface(self.model, wt.grid.z, self.viewer.ve, name="water_table",
                                 label=f"Water table · {reading}")
        if self.p_opacity.value() > 45:  # see the water table through the solids
            self.p_opacity.setValue(40)
        self.log(f"Water table ({reading}) from {len(wt.wells)} wells{(' · ' + wells.note) if wells.note else ''}.")
        for _, r in v.iterrows():
            name = self.project.legend.get(r["code"]).name
            extra = f", storage {r['storage_mcm']:,.2f} MCM" if "storage_mcm" in r and r["storage_mcm"] == r["storage_mcm"] else ""
            self.log(f"  {name}: {r['saturated_mcm']:,.1f} of {r['volume_mcm']:,.1f} MCM saturated "
                     f"({r['saturated_pct']:.0f} %){extra}")
        self.docs.setCurrentWidget(self.viewer)

    def property_model(self):
        if not self._need_model():
            return
        from ..property3d import build_property, parameters, property_slices

        params = parameters(self.project)
        if not params:
            QMessageBox.information(self, "Property model", "No downhole readings (Downhole sheet).")
            return
        dlg = PropertyDialog(params, self)
        if dlg.exec() != QDialog.Accepted:
            return
        param, lo, hi = dlg.values()
        datum = self.p_datum.currentData()

        def done(pm):
            self.property = pm
            ve = self.p_ve.value() or self._auto_ve()
            self.viewer.show_property(pm, ve, lo, hi)
            st = pm.stats()
            self.log(f"{param} model: {st['min']:.4g}–{st['max']:.4g} {pm.unit}; shown "
                     f"{lo if lo is not None else st['min']:.4g}–{hi if hi is not None else st['max']:.4g}, "
                     f"volume {pm.volume_between(lo, hi) / 1e6:,.2f} MCM")
            self.docs.setCurrentWidget(self.viewer)

        self.run(f"Interpolating {param} in 3D", build_property, done, self.project, self.model, param,
                 datum=datum)

    def strat_model(self):
        if not self.need_project():
            return
        dlg = StratDialog(self.project, self)
        if dlg.exec() != QDialog.Accepted:
            return
        from ..strat import build_strat_model

        order = dlg.values()
        b = self.boundary if self.p_clipb.isChecked() else None

        def done(model):
            self.model = model
            self._refresh_tree()
            self.redraw(reset_view=True)
            self._fill_volumes()
            self.log(f"Stratigraphic model: {' / '.join(self.project.legend.get(c).name for c in order)}")
            self.docs.setCurrentWidget(self.viewer)

        self.run("Building stratigraphic model", build_strat_model, done, self.project, order,
                 self.p_cell.value() or None, self.p_dz.value() or None, boundary=b)

    def hydrochemistry(self):
        path, _ = QFileDialog.getOpenFileName(self, "Water-quality data", "", "Chemistry (*.xlsx *.xls *.csv)")
        if not path:
            return
        from ..hydrochem import analyse, load_chemistry

        try:
            df = load_chemistry(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Hydrochemistry", str(e))
            return
        self.doc_chem.set_data(df, self._title())
        res = analyse(df)
        self.chem_results = res
        self.log(f"Hydrochemistry: {len(df)} samples; water types " +
                 ", ".join(f"{k} ({v})" for k, v in res["water_type"].value_counts().items()))
        bad = res[~res["balance_ok_5pct"]]
        if len(bad):
            self.log(f"  ionic balance outside ±5 %: {', '.join(bad['sample'])}")
        self.docs.setCurrentWidget(self.doc_chem)

    def show_fractures(self):
        if not self.need_project():
            return
        from ..fractures import fracture_figure

        try:
            fig = fracture_figure(self.project, None, self._title())
        except ValueError as e:
            QMessageBox.information(self, "Fractures", str(e))
            return
        self.doc_fract.set_figure(fig)
        self.docs.setCurrentWidget(self.doc_fract)

    # ------------------------------------------------------------------ export
    def save_image(self):
        w = self.docs.currentWidget()
        is3d = w is self.viewer
        if not is3d and not (isinstance(w, FigureDoc) and w.figure is not None):
            QMessageBox.information(self, "Save image", "Open the 3D model or a log, section, map first.")
            return
        page_mm = None if is3d else w.figure.get_size_inches()[0] * 25.4
        dlg = ExportImageDialog(is3d, page_mm, self)
        if dlg.exec() != QDialog.Accepted:
            return
        width_mm, dpi, ext = dlg.values()
        path, _ = QFileDialog.getSaveFileName(self, "Save image", f"litholog.{ext}",
                                              "PNG (*.png);;TIFF (*.tif);;JPEG (*.jpg)")
        if not path:
            return
        px = int(round(width_mm / 25.4 * dpi))

        def work():
            if is3d:
                return self.viewer.export_image(path, px, dpi)
            from PIL import Image

            Image.MAX_IMAGE_PIXELS = None
            kw = {"pil_kwargs": {"compression": "tiff_lzw"}} if path.lower().endswith((".tif", ".tiff")) else {}
            w.figure.savefig(path, dpi=dpi, **kw)
            return path

        self.busy.show()
        self.log(f"Rendering {px:,} px wide image at {dpi} dpi …")
        QApplication.processEvents()
        try:
            work()   # rendering must stay on the GUI thread (OpenGL)
            self.log(f"Saved {path}  ({width_mm:.0f} mm at {dpi} dpi)")
        except MemoryError:
            QMessageBox.warning(self, "Save image", "Not enough memory for this size. Use a smaller width or "
                                                    "DPI, or save the page as PDF/SVG (vector, any zoom).")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Save image", str(e))
        finally:
            self.busy.hide()

    def save_page(self):
        w = self.docs.currentWidget()
        if not isinstance(w, FigureDoc) or w.figure is None:
            QMessageBox.information(self, "Save page", "Open a strip log, section, fence or map first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save page", "litholog.pdf", "PDF (*.pdf);;SVG (*.svg)")
        if path:
            w.figure.savefig(path)
            self.log(f"Saved {path}")

    def export_grid(self):
        if self._current_map is None:
            QMessageBox.information(self, "Grid", "Draw a map first (Maps ▸ New map).")
            return
        from ..grid import write_ascii_grid

        path, _ = QFileDialog.getSaveFileName(self, "Save grid", "grid.asc", "ESRI ASCII grid (*.asc)")
        if path:
            write_ascii_grid(self._current_map, path)
            self.log(f"Saved {path}")

    def _need_model(self):
        if self.model is None:
            QMessageBox.information(self, "3D model", "Build the model first (3D Model ▸ Build model).")
            return False
        return True

    def export_html(self):
        if not self._need_model():
            return
        from ..solid import build_solids, solid_figure

        path, _ = QFileDialog.getSaveFileName(self, "Save interactive 3D page", "model_3d.html", "HTML (*.html)")
        if path:
            fig, _ = solid_figure(self.model, build_solids(self.model), self.project.legend,
                                  self.p_ve.value() or None, self._title(), sy=self._sy())
            fig.write_html(path, include_plotlyjs=True)
            self.log(f"Saved {path}")

    def export_meshes(self):
        if not self._need_model():
            return
        folder = QFileDialog.getExistingDirectory(self, "Folder for solids (OBJ, STL, VTP)")
        if not folder:
            return
        from ..solid import build_solids
        from .viewer3d import solid_to_mesh

        for s in build_solids(self.model, self.p_smooth.value() / 4):
            mesh = solid_to_mesh(s)
            stem = Path(folder) / f"solid_{s.code}"
            for ext in (".obj", ".stl", ".vtp"):
                mesh.save(str(stem) + ext) if ext != ".obj" else _save_obj(mesh, str(stem) + ext)
        self.log(f"Saved solids (OBJ, STL, VTP; true elevations) to {folder}")

    def export_vtk(self):
        if not self._need_model():
            return
        from ..model3d import write_vtk

        path, _ = QFileDialog.getSaveFileName(self, "Save model for ParaView", "model.vtk", "VTK (*.vtk)")
        if path:
            write_vtk(self.model, path)
            self.log(f"Saved {path}")

    def export_volumes(self):
        if not self._need_model():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save volumes", "volumes.csv", "CSV (*.csv)")
        if path:
            vols = self.model.volumes(self._sy())
            vols.insert(1, "name", [self.project.legend.get(c).name for c in vols["code"]])
            vols.to_csv(path, index=False)
            self.log(f"Saved {path}")


def _sync_parent(item):
    """Tick state of a group item from its children (without touching the children)."""
    states = {item.child(k).checkState(0) for k in range(item.childCount())}
    item.setCheckState(0, Qt.Checked if states == {Qt.Checked} else
                       Qt.Unchecked if states == {Qt.Unchecked} else Qt.PartiallyChecked)


def _save_obj(mesh, path):
    import pyvista as pv

    pl = pv.Plotter(off_screen=True)
    pl.add_mesh(mesh)
    pl.export_obj(path)
    pl.close()


class SectionDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New cross-section")
        self.resize(560, 520)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.name = QLineEdit("A-A'")
        self.ve = QDoubleSpinBox(maximum=10000, singleStep=5, decimals=0, specialValueText="Fit page")
        self.datum = QComboBox()
        self.datum.addItem("Elevation", "elevation")
        self.datum.addItem("Depth (flat ground)", "depth")
        self.style = QCheckBox("Log section (strip logs along the line)")
        self.curve = QComboBox()
        self.curve.addItem("No curve", None)
        from ..property3d import parameters

        for prm in parameters(project):
            self.curve.addItem(prm, prm)
        f.addRow("Name", self.name)
        f.addRow("Vertical exaggeration", self.ve)
        f.addRow("Hang holes by", self.datum)
        f.addRow("", self.style)
        f.addRow("Curve beside logs", self.curve)
        v.addLayout(f)
        h = QHBoxLayout()
        self.all = QListWidget()
        self.all.addItems(project.ids)
        self.all.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.sel = QListWidget()
        self.sel.setDragDropMode(QAbstractItemView.InternalMove)
        mid = QVBoxLayout()
        add = QPushButton("Add ▶")
        rem = QPushButton("◀ Remove")
        add.clicked.connect(self._add)
        rem.clicked.connect(lambda: [self.sel.takeItem(self.sel.row(i)) for i in self.sel.selectedItems()])
        self.all.itemDoubleClicked.connect(lambda it: self.sel.addItem(it.text()))
        mid.addStretch(1)
        mid.addWidget(add)
        mid.addWidget(rem)
        mid.addStretch(1)
        for title, wdg in (("Boreholes", self.all), ("Section (drag to reorder)", self.sel)):
            box = QVBoxLayout()
            lab = QLabel(title)
            lab.setObjectName("Dim")
            box.addWidget(lab)
            box.addWidget(wdg)
            h.addLayout(box)
            if wdg is self.all:
                h.addLayout(mid)
        v.addLayout(h)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _add(self):
        for it in self.all.selectedItems():
            self.sel.addItem(it.text())

    def _ok(self):
        if self.sel.count() < 2:
            QMessageBox.information(self, "Section", "Add at least two boreholes.")
            return
        self.accept()

    def values(self):
        ids = [self.sel.item(i).text() for i in range(self.sel.count())]
        return (ids, self.name.text() or "A-A'", self.ve.value(), self.datum.currentData(),
                "logs" if self.style.isChecked() else "section", self.curve.currentData())


class MapDialog(QDialog):
    def __init__(self, project, has_boundary, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New contour map")
        f = QFormLayout(self)
        self.kind = QComboBox()
        for k, label in MAP_KINDS.items():
            self.kind.addItem(label, k)
        self.unit = QComboBox()
        for c in dict.fromkeys(c for c in project.lithology["code"] if c):
            self.unit.addItem(f"{project.legend.get(c).name} ({c})", c)
        self.method = QComboBox()
        for label, val in (("Inverse distance (honours data)", "idw"), ("Ordinary kriging", "kriging"),
                           ("Linear (TIN)", "linear")):
            self.method.addItem(label, val)
        self.cell = QDoubleSpinBox(maximum=1e5, singleStep=50, decimals=0, suffix=" m", specialValueText="Auto")
        self.clip = QCheckBox("Clip to study area")
        self.clip.setChecked(has_boundary)
        self.clip.setEnabled(has_boundary)
        f.addRow("Map", self.kind)
        f.addRow("Unit", self.unit)
        f.addRow("Gridding", self.method)
        f.addRow("Cell size", self.cell)
        f.addRow("", self.clip)
        self.kind.currentIndexChanged.connect(
            lambda: self.unit.setEnabled(self.kind.currentData() in ("top", "base", "depth", "thickness")))
        self.kind.setCurrentIndex(list(MAP_KINDS).index("thickness"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def values(self):
        k = self.kind.currentData()
        attr = f"{k}:{self.unit.currentData()}" if k in ("top", "base", "depth", "thickness") else k
        return attr, self.method.currentData(), self.cell.value(), self.clip.isChecked()


class PropertyDialog(QDialog):
    def __init__(self, params, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D property model")
        f = QFormLayout(self)
        self.param = QComboBox()
        self.param.addItems(params)
        self.use_lo = QCheckBox("Show values from")
        self.lo = QDoubleSpinBox(minimum=-1e9, maximum=1e9, decimals=3)
        self.use_hi = QCheckBox("Show values up to")
        self.hi = QDoubleSpinBox(minimum=-1e9, maximum=1e9, decimals=3, value=100)
        f.addRow("Parameter", self.param)
        f.addRow(self.use_lo, self.lo)
        f.addRow(self.use_hi, self.hi)
        hint = QLabel("e.g. resistivity up to 100 ohm-m to see low-resistivity (weathered/fractured) zones.")
        hint.setObjectName("Dim")
        hint.setWordWrap(True)
        f.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def values(self):
        return (self.param.currentText(), self.lo.value() if self.use_lo.isChecked() else None,
                self.hi.value() if self.use_hi.isChecked() else None)


class StratDialog(QDialog):
    """Pick formations and put them in order, top to bottom."""

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stratigraphic model")
        self.resize(420, 460)
        v = QVBoxLayout(self)
        lab = QLabel("Tick the formations and drag them into order, top (youngest) to bottom. "
                     "Each formation should occur once per hole; repeats use their first top.")
        lab.setWordWrap(True)
        lab.setObjectName("Dim")
        v.addWidget(lab)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        codes = list(dict.fromkeys(c for c in project.lithology["code"] if c))
        # initial order: by average top depth
        depth = project.lithology.groupby("code")["from"].mean()
        for c in sorted(codes, key=lambda c: depth.get(c, 0)):
            it = QListWidgetItem(swatch(project.legend.get(c).color), f"{project.legend.get(c).name}  ({c})")
            it.setData(Qt.UserRole, c)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.list.addItem(it)
        v.addWidget(self.list)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


class ChemDoc(QWidget):
    """Hydrochemistry document: pick a diagram or the results table."""

    DIAGRAMS = ["Piper", "Durov", "Stiff", "USSL", "Wilcox", "Gibbs", "Results table"]

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setContentsMargins(8, 6, 8, 6)
        self.combo = QComboBox()
        self.combo.addItems(self.DIAGRAMS)
        self.combo.currentIndexChanged.connect(self._show)
        top.addWidget(QLabel("Diagram"))
        top.addWidget(self.combo)
        top.addStretch(1)
        v.addLayout(top)
        self.fig = FigureDoc("Analysis ▸ Hydrochemistry to open water-quality data "
                             "(Sample, Ca, Mg, Na, K, HCO3, CO3, Cl, SO4, EC, TDS, Group).")
        self.table = QTableWidget()
        self.table.hide()
        v.addWidget(self.fig, 1)
        v.addWidget(self.table, 1)
        self.df = None
        self.title = ""

    def set_data(self, df, title=""):
        self.df, self.title = df, title
        self._show()

    def _show(self):
        if self.df is None:
            return
        import matplotlib.pyplot as plt

        from .. import hydrochem as hc

        name = self.combo.currentText()
        res = hc.analyse(self.df)
        if name == "Results table":
            self.fig.hide()
            self.table.show()
            cols = [c for c in res.columns if not c.endswith("_meq")]
            self.table.setColumnCount(len(cols))
            self.table.setRowCount(len(res))
            self.table.setHorizontalHeaderLabels(cols)
            for i, (_, r) in enumerate(res[cols].iterrows()):
                for j, c in enumerate(cols):
                    self.table.setItem(i, j, QTableWidgetItem(str(r[c])))
            self.table.resizeColumnsToContents()
            return
        self.table.hide()
        self.fig.show()
        has_ec = "ec" in self.df and self.df["ec"].notna().any()
        if name == "Stiff":
            fig = hc.stiff(self.df)
        elif name == "Gibbs":
            fig = hc.gibbs(self.df)
        else:
            fig, ax = plt.subplots(figsize=(9, 8))
            if name == "Piper":
                hc.piper(self.df, ax, f"Piper diagram – {self.title}" if self.title else "Piper diagram")
            elif name == "Durov":
                hc.durov(self.df, ax)
            elif name in ("USSL", "Wilcox") and not has_ec:
                ax.text(0.5, 0.5, "EC is needed for this diagram", ha="center", transform=ax.transAxes)
                ax.set_axis_off()
            elif name == "USSL":
                hc.ussl(self.df, res, ax)
            else:
                hc.wilcox(self.df, res, ax)
        self.fig.set_figure(fig)


class ExportImageDialog(QDialog):
    """Print size and resolution for image export (default 1000 dpi)."""

    PRESETS = [("Journal column (90 mm)", 90), ("Journal page width (180 mm)", 180), ("A4 landscape (277 mm)", 277),
               ("A3 landscape (400 mm)", 400)]

    def __init__(self, is3d, page_mm=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save image")
        f = QFormLayout(self)
        self.size = QComboBox()
        for label, mm in self.PRESETS:
            self.size.addItem(label, mm)
        if page_mm:
            self.size.insertItem(0, f"Page size ({page_mm:.0f} mm)", page_mm)
        self.size.setCurrentIndex(0 if page_mm else 1)
        self.width = QDoubleSpinBox(minimum=20, maximum=1200, decimals=0, suffix=" mm")
        self.width.setValue(self.size.currentData())
        self.size.currentIndexChanged.connect(lambda _: self.width.setValue(self.size.currentData()))
        self.dpi = QComboBox()
        for d in (300, 600, 1000, 1200):
            self.dpi.addItem(f"{d} dpi", d)
        self.dpi.setCurrentIndex(2)
        self.fmt = QComboBox()
        for label, ext in (("PNG (lossless)", "png"), ("TIFF (LZW, for print)", "tif"), ("JPEG", "jpg")):
            self.fmt.addItem(label, ext)
        self.info = QLabel()
        self.info.setObjectName("Dim")
        self.info.setWordWrap(True)
        f.addRow("Size", self.size)
        f.addRow("Width", self.width)
        f.addRow("Resolution", self.dpi)
        f.addRow("Format", self.fmt)
        f.addRow(self.info)
        if is3d:
            n = QLabel("The 3D scene is re-rendered at full resolution (not enlarged); the legend bar is "
                       "added below it.")
            n.setObjectName("Dim")
            n.setWordWrap(True)
            f.addRow(n)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        for w in (self.width, self.dpi):
            (w.valueChanged if w is self.width else w.currentIndexChanged).connect(self._info)
        self._info()

    def _info(self, *_):
        px = self.width.value() / 25.4 * self.dpi.currentData()
        self.info.setText(f"{px:,.0f} pixels wide")

    def values(self):
        return self.width.value(), self.dpi.currentData(), self.fmt.currentData()
