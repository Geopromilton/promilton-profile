"""LithoLog Studio main window."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
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
        self.setWindowIcon(theme.icon("mdi6.layers-triple", theme.ACCENT))
        self.resize(1680, 980)
        self.pool = QThreadPool.globalInstance()
        self.project = None
        self.boundary = None
        self.model = None
        self.solids = None
        self.data_path = None
        self.legend_path = None
        self.boundary_path = None
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
        self.setMenuWidget(r)

    def _build_documents(self):
        self.docs = QTabWidget()
        self.docs.setObjectName("Documents")
        self.docs.setDocumentMode(True)
        self.viewer = Viewer3D()
        self.viewer.message.connect(self.log)
        self.doc_log = FigureDoc("Select a borehole in the Project panel and click Boreholes ▸ Strip log.")
        self.doc_sec = FigureDoc("Sections ▸ New section to draw a cross-section.")
        self.doc_fence = FigureDoc("Sections ▸ Fence diagram.")
        self.doc_map = FigureDoc("Maps ▸ New map to draw a contour map.")
        for w, name, ic in [(self.viewer, "3D Model", "mdi6.cube-outline"),
                            (self.doc_log, "Strip Log", "mdi6.format-list-text"),
                            (self.doc_sec, "Cross-Section", "mdi6.chart-timeline-variant"),
                            (self.doc_fence, "Fence", "mdi6.fence"),
                            (self.doc_map, "Map", "mdi6.map-outline")]:
            self.docs.addTab(w, theme.icon(ic, theme.TEXT_DIM), name)
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
        self.p_datum = QComboBox()
        self.p_datum.addItem("Depth below ground (hard rock)", "depth")
        self.p_datum.addItem("Elevation (layered sediments)", "elevation")
        self.p_cell = QDoubleSpinBox(maximum=1e5, singleStep=50, decimals=0, suffix=" m", specialValueText="Auto")
        self.p_dz = QDoubleSpinBox(maximum=1000, singleStep=0.5, decimals=1, suffix=" m", specialValueText="Auto")
        self.p_clipb = QCheckBox("Clip to study area")
        self.p_clipb.setChecked(True)
        self.p_smooth = QSlider(Qt.Horizontal, minimum=0, maximum=12, value=4)
        f.addRow("Correlate at", self.p_datum)
        f.addRow("Cell (XY)", self.p_cell)
        f.addRow("Cell (Z)", self.p_dz)
        f.addRow("Smoothing", self.p_smooth)
        f.addRow("", self.p_clipb)
        b = QPushButton(theme.icon("mdi6.cube-outline", "#1B1F26"), "  Build model")
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
        self.p_opacity.valueChanged.connect(lambda val: self.viewer.set_opacity(val / 100))
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
        gv.addWidget(self.vol)
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
                "boundary": self.p_bnd.isChecked(), "specific_yield": self._sy()}

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
            save(path, self.project.name, self.data_path, self.legend_path, self.boundary_path, self.settings())
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
        self.load(pf["data"], legend=pf.get("legend"), name=pf.get("name"), boundary=pf.get("boundary"))

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
        path, _ = QFileDialog.getOpenFileName(self, "Open study-area boundary", "", "Shapefile (*.shp)")
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
        if self.boundary is not None:
            it = QTreeWidgetItem(root, [f"Study area · {self.boundary.area / 1e6:,.1f} km²"])
            it.setIcon(0, theme.icon("mdi6.vector-polygon", "#E0524F"))
        if self.model is not None:
            mu = QTreeWidgetItem(root, ["3D model units"])
            mu.setIcon(0, theme.icon("mdi6.cube-outline", theme.TEXT_DIM))
            for c in self.model.codes:
                it = QTreeWidgetItem(mu, [self.project.legend.get(c).name])
                it.setIcon(0, swatch(self.project.legend.get(c).color))
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Checked)
                it.setData(0, Qt.UserRole, ("unit", c))
        t.expandAll()
        bh.setExpanded(len(self.project.ids) <= 30)
        t.blockSignals(False)

    def _tree_changed(self, item, col):
        tag = item.data(0, Qt.UserRole)
        if tag and tag[0] == "unit":
            self.viewer.set_unit_visible(tag[1], item.checkState(0) == Qt.Checked)

    def _tree_double(self, item, col):
        tag = item.data(0, Qt.UserRole)
        if tag and tag[0] == "borehole":
            self.show_striplog(bid=tag[1])

    def _selected_borehole(self):
        it = self.tree.currentItem()
        tag = it.data(0, Qt.UserRole) if it else None
        if tag and tag[0] == "borehole":
            return tag[1]
        return self.project.ids[0] if self.project and self.project.ids else None

    # ------------------------------------------------------------------ 3D model
    def build_model(self):
        if not self.need_project():
            return
        from ..model3d import build_model

        cell = self.p_cell.value() or None
        dz = self.p_dz.value() or None
        b = self.boundary if self.p_clipb.isChecked() else None

        def done(model):
            self.model = model
            self._refresh_tree()
            nz, ny, nx = model.lith.shape
            self.log(f"Model built: {nx} × {ny} × {nz} voxels ({model.cell:g} × {model.cell:g} × {model.dz:g} m)"
                     + (f"; clipped to study area, {100 * (1 - model.coverage):.0f} % beyond borehole cover"
                        if model.coverage is not None else ""))
            self.redraw(reset_view=True)
            self._fill_volumes(getattr(self, "_pending_sy", None) or None)
            self._pending_sy = None
            self.docs.setCurrentWidget(self.viewer)

        self.run("Building 3D model", build_model, done, self.project, cell, dz,
                 datum=self.p_datum.currentData(), boundary=b)

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
        self.solids = build_solids(self.model, self.p_smooth.value() / 4, cut)
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
        note = "MCM = million m³, ground to base of drilling"
        if m.boundary is not None:
            note += f", inside the study area ({m.boundary.area / 1e6:,.1f} km²)"
        self.vol_note.setText(note + ". Storage = volume × specific yield (your estimate).")

    def _sy_changed(self, item):
        if item.column() == 3 and self.model is not None:
            self._fill_volumes(self._sy())

    # ------------------------------------------------------------------ 2D documents
    def show_striplog(self, checked=False, bid=None):
        if not self.need_project():
            return
        from ..striplog import Style, striplog_pages

        bid = bid or self._selected_borehole()
        fig = next(iter(striplog_pages(self.project.borehole(bid), self.project.legend,
                                       Style(project_name=self._title()))))
        self.doc_log.set_figure(fig)
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
        ids, name, ve, datum = dlg.values()
        from ..section import section_figure, through_boreholes

        try:
            line = through_boreholes(self.project, ids, name)
            fig = section_figure(self.project, line, ve=ve or None, title=self._title(), datum=datum)
        except ValueError as e:
            QMessageBox.warning(self, "Section", str(e))
            return
        self.doc_sec.set_figure(fig)
        self.docs.setCurrentWidget(self.doc_sec)
        self.log(f"Section {name}: {len(ids)} boreholes, {line.length:,.0f} m.")

    def show_fence(self):
        if not self.need_project():
            return
        from ..fence import fence_figure, network_edges

        edges = network_edges(self.project, None, "mst")
        fig = fence_figure(self.project, edges, title=self._title())
        self.doc_fence.set_figure(fig)
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
        fig = map_figure(g, vals, attr, legend=self.project.legend, method=method, title=self._title(),
                         all_xy=self.project.boreholes)
        self._current_map = g
        self.doc_map.set_figure(fig)
        self.docs.setCurrentWidget(self.doc_map)
        self.log(f"Map {attr} ({method}).")

    # ------------------------------------------------------------------ export
    def save_image(self):
        w = self.docs.currentWidget()
        path, _ = QFileDialog.getSaveFileName(self, "Save image", "litholog.png", "PNG image (*.png)")
        if not path:
            return
        if w is self.viewer:
            self.viewer.screenshot(path, scale=3)
        elif isinstance(w, FigureDoc) and w.figure is not None:
            w.figure.savefig(path, dpi=300)
        self.log(f"Saved {path}")

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
        f.addRow("Name", self.name)
        f.addRow("Vertical exaggeration", self.ve)
        f.addRow("Hang holes by", self.datum)
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
        return ids, self.name.text() or "A-A'", self.ve.value(), self.datum.currentData()


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
