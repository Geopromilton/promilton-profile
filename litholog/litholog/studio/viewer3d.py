"""High-quality 3D viewer (VTK through PyVista) embedded in Qt."""

from __future__ import annotations

import numpy as np
import pyvista as pv
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from . import theme

VIEW_DIRS = {  # camera direction (from focal point towards the camera), view-up
    "iso_sw": ((-1, -1.1, 0.9), (0, 0, 1)),
    "iso_se": ((1.1, -1, 0.9), (0, 0, 1)),
    "iso_ne": ((1, 1.1, 0.9), (0, 0, 1)),
    "iso_nw": ((-1.1, 1, 0.9), (0, 0, 1)),
    "top": ((0, 0, 1), (0, 1, 0)),
    "bottom": ((0, 0, -1), (0, 1, 0)),
    "front": ((0, -1, 0), (0, 0, 1)),
    "back": ((0, 1, 0), (0, 0, 1)),
    "left": ((-1, 0, 0), (0, 0, 1)),
    "right": ((1, 0, 0), (0, 0, 1)),
}


def solid_to_mesh(solid) -> pv.PolyData:
    faces = np.hstack([np.full((len(solid.faces), 1), 3, np.int64), solid.faces.astype(np.int64)]).ravel()
    mesh = pv.PolyData(solid.verts.astype(np.float64), faces)
    return mesh.compute_normals(split_vertices=False, auto_orient_normals=True)


class Viewer3D(QWidget):
    message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self, auto_update=False)
        lay.addWidget(self.plotter.interactor)
        p = self.plotter
        p.set_background(theme.VIEW_BG_BOTTOM, top=theme.VIEW_BG_TOP)
        try:
            p.enable_anti_aliasing("fxaa")
        except Exception:  # noqa: BLE001 - older/limited GL: carry on without AA
            pass
        p.add_axes(interactive=False, line_width=2, color=theme.TEXT, xlabel="E", ylabel="N", zlabel="Up")
        self.units = {}          # code -> actor
        self.extras = {}         # name -> actor (boreholes, labels, boundary, grid)
        self.ve = 1.0
        self._clip_plane = None
        self._model = None
        self._welcome()

    # ------------------------------------------------------------------
    def _welcome(self):
        self.plotter.add_text("LithoLog Studio\nOpen borehole data to begin  (Home ▸ Open)",
                              position="upper_left", font_size=11, color=theme.TEXT_DIM, name="welcome")
        self.plotter.render()

    def clear(self):
        self.disable_clip()
        self.plotter.clear_actors()
        self.units.clear()
        self.extras.clear()

    def show_model(self, model, solids, legend, ve: float, boreholes=True, labels=True, boundary=True,
                   opacity=1.0, cutaway=None):
        """Draw smooth solids, boreholes and boundary. z is exaggerated by ``ve``."""
        self.clear()
        self._model = model
        self.ve = ve
        p = self.plotter
        for s in solids:
            mesh = solid_to_mesh(s)
            mesh.points[:, 2] *= ve
            lt = legend.get(s.code)
            self.units[s.code] = p.add_mesh(
                mesh, color=lt.color, smooth_shading=True, opacity=opacity, name=f"unit_{s.code}",
                ambient=0.28, diffuse=0.78, specular=0.18, specular_power=18, show_scalar_bar=False)
        if boreholes and model.holes:
            self._add_boreholes(model, legend, ve, labels, cutaway)
        if boundary and model.boundary is not None:
            for k, r in enumerate(model.boundary.rings):
                pts = np.column_stack([r[:, 0], r[:, 1], np.full(len(r), model.z[0] * ve)])
                line = pv.lines_from_points(np.vstack([pts, pts[:1]]))
                self.extras[f"boundary{k}"] = p.add_mesh(line, color="#E0524F", line_width=3,
                                                         name=f"boundary{k}")
        self._grid(model, ve)
        p.reset_camera()
        self.set_view("iso_sw")

    def _add_boreholes(self, model, legend, ve, labels, cutaway):
        p = self.plotter
        span = max(model.x[-1] - model.x[0], model.y[-1] - model.y[0])
        radius = span * 0.0022
        holes = model.holes
        if cutaway:
            xm, ym = np.median(model.x), np.median(model.y)
            holes = [h for h in holes if not ((h[1] < xm if "w" in cutaway else h[1] > xm)
                                              and (h[2] < ym if "s" in cutaway else h[2] > ym))]
        blocks = pv.MultiBlock()
        colors = []
        tops = []
        for bid, x, y, us in holes:
            for u in us:
                seg = pv.Line((x, y, u.top * ve), (x, y, u.bot * ve)).tube(radius=radius, n_sides=14)
                blocks.append(seg)
                colors.append(legend.get(u.code).color)
            tops.append((bid, (x, y, us[0].top * ve + span * 0.004)))
        for k, (seg, col) in enumerate(zip(blocks, colors)):
            p.add_mesh(seg, color=col, smooth_shading=True, name=f"bh_{k}", ambient=0.3, specular=0.3)
        if labels and tops:
            self.extras["labels"] = p.add_point_labels(
                np.array([t[1] for t in tops]), [t[0] for t in tops], font_size=11, text_color="white",
                shape=None, show_points=False, always_visible=True, name="bh_labels", bold=True)

    def _grid(self, model, ve):
        """Bounding grid with true coordinates (the geometry's z is exaggerated by ``ve``)."""
        p = self.plotter
        b = p.bounds
        self.extras["grid"] = p.show_grid(
            color=theme.TEXT_DIM, font_size=9, xtitle="Easting (m)", ytitle="Northing (m)",
            ztitle=f"Elevation (m)   VE ×{ve:g}", n_xlabels=5, n_ylabels=5, n_zlabels=5, fmt="%.0f",
            location="outer", ticks="outside", minor_ticks=False,
            axes_ranges=[b[0], b[1], b[2], b[3], b[4] / ve, b[5] / ve])

    # ------------------------------------------------------------------
    def set_view(self, name: str):
        if name not in VIEW_DIRS:
            return
        d, up = VIEW_DIRS[name]
        p = self.plotter
        b = p.bounds
        c = np.array([(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2])
        dist = max(b[1] - b[0], b[3] - b[2], b[5] - b[4]) * 2.2
        d = np.asarray(d, float) / np.linalg.norm(d)
        p.camera_position = [tuple(c + d * dist), tuple(c), up]
        ortho = name in ("top", "bottom", "front", "back", "left", "right")
        p.camera.parallel_projection = ortho
        p.reset_camera()
        if ortho:
            # Fit the visible face: horizontal and vertical half-extents on screen.
            ext = {"top": (b[1] - b[0], b[3] - b[2]), "bottom": (b[1] - b[0], b[3] - b[2]),
                   "front": (b[1] - b[0], b[5] - b[4]), "back": (b[1] - b[0], b[5] - b[4]),
                   "left": (b[3] - b[2], b[5] - b[4]), "right": (b[3] - b[2], b[5] - b[4])}[name]
            w, h = max(self.width(), 1), max(self.height(), 1)
            p.camera.parallel_scale = 0.56 * max(ext[1], ext[0] * h / w)
        else:
            p.camera.zoom(1.15)
        p.render()

    def set_unit_visible(self, code, visible: bool):
        a = self.units.get(code)
        if a is not None:
            a.SetVisibility(bool(visible))
            self.plotter.render()

    def set_opacity(self, value: float):
        for a in self.units.values():
            a.GetProperty().SetOpacity(value)
        self.plotter.render()

    def set_extras_visible(self, prefix: str, visible: bool):
        for name, actor in list(self.plotter.renderer.actors.items()):
            if name.startswith(prefix):
                actor.SetVisibility(bool(visible))
        self.plotter.render()

    # ------------------------------------------------------------------
    def enable_clip(self, normal="x"):
        """Interactive cutting plane applied to every lithology solid."""
        import vtk

        self.disable_clip()
        plane = vtk.vtkPlane()
        self._clip_plane = plane
        for a in self.units.values():
            a.GetMapper().AddClippingPlane(plane)

        def moved(n, origin):
            plane.SetNormal(*n)
            plane.SetOrigin(*origin)
            self.plotter.render()

        self.plotter.add_plane_widget(moved, normal=normal, color=theme.ACCENT, outline_translation=False,
                                      normal_rotation=True, implicit=True)
        self.message.emit("Drag the amber plane to cut the model; drag its arrow to tilt it.")

    def disable_clip(self):
        if self._clip_plane is not None:
            for a in self.units.values():
                a.GetMapper().RemoveAllClippingPlanes()
            self._clip_plane = None
        try:
            self.plotter.clear_plane_widgets()
        except Exception:  # noqa: BLE001
            pass
        self.plotter.render()

    def screenshot(self, path, scale: int = 3, transparent=False):
        self.plotter.screenshot(str(path), scale=scale, transparent_background=transparent)
        return path
