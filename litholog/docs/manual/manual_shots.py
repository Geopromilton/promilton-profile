"""Capture the LithoLog Studio screenshots used in the user manual (tutorial data)."""
import sys
import time
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication

from litholog.studio import theme

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
app = QApplication(sys.argv[:1])
theme.apply(app, "dark")
from litholog.studio import mainwindow as mw  # noqa: E402

w = mw.MainWindow()
w.resize(1600, 960)
w.move(0, 0)
w.show()
T = mw.TUTORIAL


def pump(n=25):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.04)


def wait(cond, t=400):
    t0 = time.time()
    while not cond() and time.time() - t0 < t:
        app.processEvents()
        time.sleep(0.05)


def shot(name, widget=None, rect=None):
    pump(8)
    if widget is None:
        img = app.primaryScreen().grabWindow(0, 0, 0, w.frameGeometry().width(), w.frameGeometry().height())
    else:
        img = widget.grab()
    if rect is not None:
        img = img.copy(QRect(*rect))
    img.save(str(OUT / f"{name}.png"))
    print("  ", name, flush=True)


def dialog(name, dlg):
    dlg.show()
    pump(15)
    shot(name, dlg)
    dlg.close()


# ---------------------------------------------------------------- start
pump(20)
shot("00_start")
w.open_demo()
wait(lambda: w.model is not None)
pump(30)
w.p_cut.setCurrentIndex(1)
pump(30)
shot("01_main_3d")
H = 132
for k, name in enumerate(["home", "boreholes", "sections", "maps", "3dmodel", "analysis", "view"]):
    w.ribbon.tabs.setCurrentIndex(k)
    pump(6)
    shot(f"02_ribbon_{name}", rect=(0, 0, 1600, H))
w.ribbon.tabs.setCurrentIndex(0)
dock_tree = w.tree.parentWidget()
while dock_tree is not None and not dock_tree.inherits("QDockWidget"):
    dock_tree = dock_tree.parentWidget()
shot("03_project_tree", dock_tree)
props = [d for d in w.findChildren(mw.QDockWidget) if d.windowTitle() == "Properties"][0]
shot("04_properties", props)
shot("05_legend_bar", w.viewer.legend)
msgs = [d for d in w.findChildren(mw.QDockWidget) if d.windowTitle() == "Messages"][0]
shot("06_messages", msgs)

# ---------------------------------------------------------------- 2D documents
w.show_striplog(bid="TB-08")
pump(20)
shot("10_striplog")
dialog("11_section_dialog", mw.SectionDialog(w.project, w))
from litholog.section import section_figure, through_boreholes  # noqa: E402

line = through_boreholes(w.project, ["TB-01", "TB-08", "TB-15", "TB-22"], "A-A'")
w.doc_sec.set_figure(section_figure(w.project, line, legend=w.project.legend, title=w._title(), datum="elevation"))
w.docs.setCurrentWidget(w.doc_sec)
pump(20)
shot("12_section")
w.doc_sec.set_figure(section_figure(w.project, line, legend=w.project.legend, title=w._title(), datum="elevation",
                                    style="logs", curve="Resistivity"))
pump(20)
shot("13_section_logs")
w.show_fence()
pump(20)
shot("14_fence")
dialog("15_map_dialog", mw.MapDialog(w.project, True, w))
from litholog.grid import grid_attribute  # noqa: E402
from litholog.maps import map_figure  # noqa: E402

g, vals = grid_attribute(w.project, "thickness:WGN", "kriging", None, boundary=w.boundary)
w.doc_map.set_figure(map_figure(g, vals, "thickness:WGN", legend=w.project.legend, method="kriging",
                                title=w._title(), all_xy=w.project.boreholes))
w.docs.setCurrentWidget(w.doc_map)
pump(20)
shot("16_map")

# ---------------------------------------------------------------- 3D model tools
w.docs.setCurrentWidget(w.viewer)
dlg = mw.LayerPropertiesDialog if hasattr(mw, "LayerPropertiesDialog") else None
from litholog.studio.legendbar import LayerPropertiesDialog  # noqa: E402

vols = dict(zip(w.model.volumes()["code"], w.model.volumes()["volume_mcm"]))
dialog("20_layer_properties", LayerPropertiesDialog(w.project.legend, w.model.codes, w.layer_state, "FGN", vols, w))
d = mw.InfluenceDialog(w.project, w._interp_now(), w.model, w)
d.target.setCurrentIndex(3)
dialog("21_influence", d)
w._load_constraints(str(T / "tutorial_constraints.csv"), rebuild=True)
wait(lambda: w.model is not None and w.model.constraints is not None)
pump(30)
w.p_cut.setCurrentIndex(0)
pump(30)
shot("22_constraints")
# horizons: show only the fracture zones
root = w.tree.invisibleRootItem()
items, st = [], [root]
while st:
    it = st.pop()
    items.append(it)
    st += [it.child(k) for k in range(it.childCount())]
for it in items:
    tag = it.data(0, Qt.UserRole) if it is not root else None
    if tag and tag[0] == "horizon" and tag[2] != "FGN":
        it.setCheckState(0, Qt.Unchecked)
pump(30)
shot("23_horizons_only_fractures")
for it in items:
    tag = it.data(0, Qt.UserRole) if it is not root else None
    if tag and tag[0] == "horizon":
        it.setCheckState(0, Qt.Checked)
pump(20)
for name, v in (("24_view_front", "front"), ("25_view_top", "top"), ("26_view_left", "left")):
    w.view(v)
    pump(15)
    w.viewer.export_image(OUT / f"{name}.png", 1500, 150, text_pt=9)
    print("  ", name, flush=True)
w.view("iso_sw")
pump(10)
w.ribbon.tabs.setCurrentIndex(6)
w.set_texture("pattern", True)
pump(30)
shot("27_pattern_texture")
w.set_texture("grain", True)
pump(20)
w.ribbon.tabs.setCurrentIndex(4)
dialog("28_export_dialog", mw.ExportImageDialog(True, None, w))
w.viewer.enable_clip()
pump(20)
shot("29_cut_plane")
w.viewer.disable_clip()

# ---------------------------------------------------------------- analysis
with mock.patch.object(mw.QFileDialog, "getOpenFileName", return_value=(str(T / "tutorial_water_levels.csv"), "")), \
        mock.patch("PySide6.QtWidgets.QInputDialog.getItem", return_value=("Pre-monsoon", True)):
    w.aquifer()
pump(30)
w.ribbon.tabs.setCurrentIndex(5)
shot("30_aquifer_3d")
w.docs.setCurrentWidget(w.doc_map)
pump(20)
shot("31_water_table_map")
w.docs.setCurrentWidget(w.viewer)
dialog("32_recharge_dialog", mw.RechargeDialog(w.wells.readings, w.model.codes, w.project.legend,
                                                {"WGN": 0.015, "FGN": 0.01}, w))
from litholog.property3d import build_property  # noqa: E402

pm = build_property(w.project, w.model, "Resistivity")
w.viewer.show_property(pm, w.p_ve.value() or w._auto_ve(), None, 500)
pump(30)
shot("33_property_model")
dialog("34_strat_dialog", mw.StratDialog(w.project, w))
w.redraw(reset_view=True)
with mock.patch.object(mw.QFileDialog, "getOpenFileName", return_value=(str(T / "tutorial_chemistry.csv"), "")):
    w.hydrochemistry()
pump(30)
shot("35_chemistry")
w.show_fractures()
pump(25)
shot("36_fractures")
from litholog.validation import validation_report  # noqa: E402

vr = validation_report(w.project, OUT / "_cv", None, w.boundary, "FGN", w._title(), volumes=True)
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

f = Figure(figsize=(420 / 25.4, 297 / 25.4))
ax = f.add_axes([0, 0, 1, 1])
ax.imshow(plt.imread(str(OUT / "_cv" / "validation.png")))
ax.set_axis_off()
w.doc_valid.set_figure(f)
w.docs.setCurrentWidget(w.doc_valid)
pump(20)
shot("37_validation")
w.docs.setCurrentWidget(w.viewer)

# ---------------------------------------------------------------- scene, themes, prompts
w.tree.scrollToBottom()
pump(10)
shot("40_scene_tree", dock_tree)
w.viewer.set_scene("boundary", "", color="#FFD400", width=5)
dialog("41_scene_properties", mw.SceneItemDialog("Study area", "boundary", {"color": "#FFD400", "width": 5}, w))
w.set_theme("light")
w.ribbon.tabs.setCurrentIndex(6)
pump(30)
shot("42_light_theme")
w.set_theme("dark")
pump(10)
from PySide6.QtWidgets import QMessageBox  # noqa: E402

box = QMessageBox(w)
box.setIcon(QMessageBox.Warning)
box.setWindowTitle("LithoLog Studio")
box.setText("Do you want to save the changes to this project?")
box.setInformativeText("The project file keeps the data, legend and colours, boundary, DEM, constraints and all "
                       "settings. Your changes will be lost if you don't save them.")
box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
box.button(QMessageBox.Discard).setText("Don't save")
dialog("43_save_prompt", box)
box = QMessageBox(w)
box.setWindowTitle("DEM")
box.setText("Open a DEM file (GeoTIFF, SRTM .hgt, ESRI .asc), or download the free Copernicus GLO-30 DEM (30 m, "
            "ESA) for this project's area from the internet.")
box.addButton("Open file…", QMessageBox.AcceptRole)
box.addButton("Download (Copernicus 30 m)", QMessageBox.ActionRole)
box.addButton(QMessageBox.Cancel)
dialog("44_dem_dialog", box)
w._saved_key = w._state_key()
w.close()
print("done", flush=True)
