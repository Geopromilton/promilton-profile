"""High-quality 3D viewer (VTK through PyVista) embedded in Qt."""

from __future__ import annotations

import numpy as np
import pyvista as pv
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from . import render, theme
from .legendbar import LegendBar

BACKGROUNDS = {  # name -> (bottom, top) or a single colour; "theme" follows the UI theme
    "theme": None, "white": ("#FFFFFF", None), "black": ("#000000", None),
    "sky": ("#FFFFFF", "#9DB9D8"), "graphite": ("#15181E", "#3A4353"),
}

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


def solid_to_mesh(solid, split: bool = False) -> pv.PolyData:
    """Triangle mesh of a solid; ``split`` keeps sharp edges (tops vs. walls) crisp."""
    faces = np.hstack([np.full((len(solid.faces), 1), 3, np.int64), solid.faces.astype(np.int64)]).ravel()
    mesh = pv.PolyData(solid.verts.astype(np.float64), faces)
    return mesh.compute_normals(split_vertices=split, feature_angle=45, auto_orient_normals=True)


# Display options (View ▸ Rendering)
DEFAULT_LOOK = {"texture": "grain", "vivid": True, "edges": True, "ssao": False}


class Viewer3D(QWidget):
    message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.plotter = QtInteractor(self, auto_update=False)
        lay.addWidget(self.plotter.interactor, 1)
        self.legend = LegendBar(self)
        lay.addWidget(self.legend)
        p = self.plotter
        self.background = "theme"
        self.show_axes_grid = True
        self.look = dict(DEFAULT_LOOK)
        self._fs = 1.0           # line scale (> 1 while rendering a print-size image)
        self._ts = 1.0           # text scale
        self._draws = []         # drawing calls to replay for print-size export
        # Multisample anti-aliasing keeps text sharp (FXAA blurs labels and axis numbers).
        for kind, kw in (("msaa", {"multi_samples": 8}), ("ssaa", {})):
            try:
                p.enable_anti_aliasing(kind, **kw)
                break
            except Exception:  # noqa: BLE001 - limited GL: try the next / carry on without AA
                continue
        self.apply_theme(render=False)
        self.units = {}          # key (code, or code#horizon) -> actor
        self.unit_code = {}      # key -> lithology code
        self.unit_hz = {}        # key -> horizon index (None for merged solids)
        self.edges = {}          # key -> contact-line actor
        self.code_vis = {}       # code -> visible
        self.hz_vis = {}         # horizon index -> visible
        self.extras = {}         # name -> actor (boreholes, labels, boundary, grid)
        self.ve = 1.0
        self._clip_plane = None
        self._model = None
        self._welcome()

    def _bg_colors(self):
        if self.background == "theme" or self.background not in BACKGROUNDS:
            return theme.VIEW_BG_BOTTOM, theme.VIEW_BG_TOP
        return BACKGROUNDS[self.background]

    def _fg(self):
        """Text colour that reads on the current 3D background."""
        from PySide6.QtGui import QColor

        bottom, top = self._bg_colors()
        light = QColor(bottom).lightnessF() * (0.5 if top else 1) + (QColor(top).lightnessF() * 0.5 if top else 0)
        return "#1E2530" if light > 0.55 else "#E6E9EE"

    def apply_theme(self, render=True):
        """Background and axis colours after a theme or background change."""
        p = self.plotter
        bottom, top = self._bg_colors()
        p.set_background(bottom, top=top)
        try:
            p.hide_axes()
        except Exception:  # noqa: BLE001
            pass
        self._orientation_axes()
        self.legend.update()
        if render:
            p.render()

    def _orientation_axes(self):
        """N/E/Up marker with large, sharp labels at a fixed pixel size."""
        p = self.plotter
        fg = self._fg()
        p.add_axes(interactive=False, line_width=4 * self._fs, color=fg, xlabel="E", ylabel="N", zlabel="Up",
                   viewport=(0, 0, 0.16, 0.24), shaft_length=0.8, tip_length=0.25, cone_radius=0.5)
        a = getattr(p.renderer, "axes_actor", None)
        if a is None:
            return
        for cap, col in ((a.GetXAxisCaptionActor2D(), "#E0524F"), (a.GetYAxisCaptionActor2D(), "#3FB26B"),
                         (a.GetZAxisCaptionActor2D(), "#4FA3E0")):
            cap.GetTextActor().SetTextScaleModeToNone()
            render.style_text(cap.GetCaptionTextProperty(), size=17 * self._ts, bold=True, color=fg)
        a.GetXAxisShaftProperty().SetColor(*render.rgb("#E0524F"))
        a.GetXAxisTipProperty().SetColor(*render.rgb("#E0524F"))
        a.GetYAxisShaftProperty().SetColor(*render.rgb("#3FB26B"))
        a.GetYAxisTipProperty().SetColor(*render.rgb("#3FB26B"))
        a.GetZAxisShaftProperty().SetColor(*render.rgb("#4FA3E0"))
        a.GetZAxisTipProperty().SetColor(*render.rgb("#4FA3E0"))

    def set_background(self, name):
        self.background = name
        self.apply_theme()

    # ------------------------------------------------------------------
    def _welcome(self):
        t = self.plotter.add_text("LithoLog Studio\nOpen borehole data to begin  (Home ▸ Open)",
                                  position="upper_left", font_size=12, color=self._fg(), name="welcome")
        render.style_text(t.GetTextProperty(), color=self._fg())
        self.plotter.render()

    def clear(self):
        self.disable_clip()
        self.plotter.clear_actors()
        for d in (self.units, self.extras, self.unit_code, self.unit_hz, self.edges):
            d.clear()

    def show_model(self, model, solids, legend, ve: float, boreholes=True, labels=True, boundary=True,
                   opacity=1.0, cutaway=None):
        """Draw smooth solids, boreholes and boundary. z is exaggerated by ``ve``."""
        if self._fs == 1.0:
            self._draws = [("show_model", (model, solids, legend, ve),
                            dict(boreholes=boreholes, labels=labels, boundary=boundary, opacity=opacity,
                                 cutaway=cutaway))]
        self.clear()
        self._model = model
        self.ve = ve
        p = self.plotter
        self._legend = legend
        span = max(model.x[-1] - model.x[0], model.y[-1] - model.y[0]) or 1.0
        for s in solids:
            key = s.code if s.horizon is None else f"{s.code}#{s.horizon}"
            mesh = solid_to_mesh(s, split=True)
            mesh.points[:, 2] *= ve
            self.units[key] = self._add_solid(mesh, key, s, legend.get(s.code), opacity, span)
            self.unit_code[key] = s.code
            self.unit_hz[key] = s.horizon
            if self.look.get("edges"):
                self.edges[key] = self._add_contacts(mesh, key, legend.get(s.code))
        self._apply_visibility(render=False)
        if boreholes and model.holes:
            self._add_boreholes(model, legend, ve, labels, cutaway)
        if boundary and model.boundary is not None:
            for k, r in enumerate(model.boundary.rings):
                pts = np.column_stack([r[:, 0], r[:, 1], np.full(len(r), model.z[0] * ve)])
                line = pv.lines_from_points(np.vstack([pts, pts[:1]]))
                self.extras[f"boundary{k}"] = p.add_mesh(line, color="#E0524F", line_width=3 * self._fs,
                                                         name=f"boundary{k}")
        self._grid(model, ve)
        p.reset_camera()
        self.set_view("iso_sw")

    def _unit_color(self, lt):
        return render.enhance(lt.color) if self.look.get("vivid") else lt.color

    def _add_solid(self, mesh, key, solid, lt, opacity, span):
        color = self._unit_color(lt)
        kw = dict(smooth_shading=True, opacity=opacity, name=f"unit_{key}", show_scalar_bar=False,
                  ambient=0.22, diffuse=0.85, specular=0.28, specular_power=28)
        tex_kind = self.look.get("texture", "none")
        if tex_kind in ("grain", "pattern"):
            try:
                seed = sum(map(ord, solid.code)) + 31 * (solid.horizon or 0)
                img = (render.grain_texture(color, seed) if tex_kind == "grain"
                       else render.pattern_texture(lt.code, lt.name, color, lt.pattern))
                tile = span / (10 if tex_kind == "grain" else 26)
                mesh.active_texture_coordinates = render.triplanar_tcoords(
                    np.asarray(mesh.points), np.asarray(mesh.point_normals), tile, tile / 3)
                tex = pv.Texture(img)
                tex.repeat = True
                tex.interpolate = True
                tex.mipmap = True
                return self.plotter.add_mesh(mesh, texture=tex, **kw)
            except Exception as e:  # noqa: BLE001 - fall back to plain colour
                self.message.emit(f"Texture not available ({e}); using plain colour.")
        return self.plotter.add_mesh(mesh, color=color, **kw)

    def _add_contacts(self, mesh, key, lt):
        """Thin dark lines along the layer edges and contacts (like a drawn geological model)."""
        try:
            e = mesh.extract_feature_edges(feature_angle=35, boundary_edges=True, non_manifold_edges=False,
                                           manifold_edges=False)
            if e.n_points == 0:
                return None
            return self.plotter.add_mesh(e, color=render.darker(self._unit_color(lt), 0.5), line_width=1.2 * self._fs,
                                         name=f"edge_{key}", pickable=False)
        except Exception:  # noqa: BLE001
            return None

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
            import vtk

            fg = self._fg()
            for k, (bid, xyz) in enumerate(tops):
                t = vtk.vtkBillboardTextActor3D()   # 3D-anchored, screen-facing, sharp at any export size
                t.SetInput(str(bid))
                t.SetPosition(*xyz)
                tp = t.GetTextProperty()
                render.style_text(tp, size=13 * self._ts, bold=True, color=fg)
                tp.SetJustificationToCentered()
                tp.SetVerticalJustificationToBottom()
                p.add_actor(t, name=f"bh_label_{k}", reset_camera=False)
            self.extras["labels"] = True

    def _grid(self, model, ve):
        """Bounding grid with true coordinates (the geometry's z is exaggerated by ``ve``)."""
        p = self.plotter
        if not self.show_axes_grid:
            p.remove_bounds_axes()
            return
        b = p.bounds
        fg = self._fg()
        g = self.extras["grid"] = p.show_grid(
            color=fg, font_size=int(12 * self._ts), xtitle="Easting (m)", ytitle="Northing (m)",
            ztitle=f"Elevation (m), VE {ve:g}x", n_xlabels=5, n_ylabels=5, n_zlabels=5, fmt="%.0f",
            location="outer", ticks="outside", minor_ticks=False,
            axes_ranges=[b[0], b[1], b[2], b[3], b[4] / ve, b[5] / ve])
        try:   # sharp 2D text in the bundled font instead of scaled 3D text
            g.SetUseTextActor3D(False)
            # at print size the axes' text renders about twice as large as other text of the same
            # font size (VTK axis scaling), so it is scaled down to match the chosen point size
            fs, ts = self._fs, (self._ts if self._ts == 1.0 else self._ts * 0.55)
            g.SetScreenSize(12)          # text size comes from the font size alone
            g.SetLabelOffset(8 * ts)
            try:
                g.SetTitleOffset((22 * ts, 22 * ts))   # VTK >= 9.3 takes (x, y)
            except TypeError:
                g.SetTitleOffset(22 * ts)
            for ax in "XYZ":
                getattr(g, f"Get{ax}AxesLinesProperty")().SetLineWidth(1.5 * fs)
                getattr(g, f"Get{ax}AxesGridlinesProperty")().SetLineWidth(fs)
            for i in range(3):
                render.style_text(g.GetTitleTextProperty(i), size=14 * ts, bold=True, color=fg)
                render.style_text(g.GetLabelTextProperty(i), size=12 * ts, color=fg, weight="medium")
        except Exception:  # noqa: BLE001 - older VTK
            pass

    def show_surface(self, model, z, ve, color="#2E86DE", opacity=0.55, name="surface", label=None):
        """A gridded surface (e.g. the water table) in the model's XY grid."""
        if self._fs == 1.0:
            self._draws.append(("show_surface", (model, z, ve),
                                dict(color=color, opacity=opacity, name=name, label=label)))
        X, Y = np.meshgrid(model.x, model.y)
        grid = pv.StructuredGrid(X, Y, np.nan_to_num(z, nan=np.nanmin(z)) * ve)
        grid["valid"] = np.isfinite(z).ravel(order="F").astype(float)
        surf = grid.threshold(0.5, scalars="valid")
        self.extras[name] = self.plotter.add_mesh(surf, color=color, opacity=opacity, smooth_shading=True,
                                                  name=name, specular=0.4, show_scalar_bar=False)
        if label:
            t = self.plotter.add_text(label, position="lower_left", font_size=int(11 * self._ts), color=color,
                                      name=f"{name}_label")
            render.style_text(t.GetTextProperty(), color=color)
        self.plotter.render()

    def remove(self, name):
        self._draws = [d for d in self._draws if not (d[0] == "show_terrain" and name == "terrain")
                       and d[2].get("name") != name]
        self.plotter.remove_actor(name, render=False)
        self.plotter.remove_actor(f"{name}_label", render=False)
        self.extras.pop(name, None)
        self.plotter.render()

    def show_property(self, pm, ve, lo=None, hi=None, log=None, cmap=None):
        """Voxels of a property model within [lo, hi], coloured by value, with a colour bar."""
        if self._fs == 1.0:
            self._draws = [("show_property", (pm, ve), dict(lo=lo, hi=hi, log=log, cmap=cmap))]
        m = pm.model
        self.clear()
        img = pv.ImageData(dimensions=(len(m.x) + 1, len(m.y) + 1, len(m.z) + 1),
                           spacing=(m.cell, m.cell, m.dz * ve),
                           origin=(m.x[0] - m.cell / 2, m.y[0] - m.cell / 2, (m.z[0] - m.dz / 2) * ve))
        v = np.transpose(pm.values, (2, 1, 0)).ravel(order="F")
        img.cell_data[pm.parameter] = v
        finite = v[np.isfinite(v)]
        if log is None:
            log = finite.size and finite.min() > 0 and finite.max() / finite.min() > 50
        lo = finite.min() if lo is None else lo
        hi = finite.max() if hi is None else hi
        sel = img.threshold([lo, hi], scalars=pm.parameter)
        title = pm.parameter + (f" ({pm.unit})" if pm.unit else "")
        self.units["property"] = self.plotter.add_mesh(
            sel, scalars=pm.parameter, cmap=cmap or ("Spectral_r" if log else "viridis"), log_scale=bool(log),
            clim=[finite.min(), finite.max()], smooth_shading=False, name="property", show_edges=False,
            scalar_bar_args=dict(title=title, color=theme.TEXT, vertical=True, position_x=0.88,
                                 position_y=0.2, height=0.6, title_font_size=12, label_font_size=10))
        self._style_scalar_bars()
        self._model = m
        self.ve = ve
        if m.holes:
            from ..patterns import Legend

            self._add_boreholes(m, Legend(), ve, True, None)
        self._grid(m, ve)
        self.plotter.reset_camera()
        self.set_view("iso_sw")

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

    def _apply_visibility(self, render=True):
        for key, a in self.units.items():
            code, hz = self.unit_code.get(key, key), self.unit_hz.get(key)
            vis = self.code_vis.get(code, True) and (hz is None or self.hz_vis.get(hz, True))
            a.SetVisibility(bool(vis))
            e = self.edges.get(key)
            if e is not None:
                e.SetVisibility(bool(vis))
        if render:
            self.plotter.render()

    def set_unit_visible(self, code, visible: bool):
        """Show/hide a lithology (all its horizons)."""
        self.code_vis[code] = bool(visible)
        self._apply_visibility()

    def set_horizon_visible(self, k: int, visible: bool):
        self.hz_vis[int(k)] = bool(visible)
        self._apply_visibility()

    def set_opacity(self, value: float, per_unit=None):
        """Overall opacity; ``per_unit`` {code: factor} from the layer properties."""
        per_unit = per_unit or {}
        for key, a in self.units.items():
            a.GetProperty().SetOpacity(value * per_unit.get(self.unit_code.get(key, key), 1.0))
        self.plotter.render()

    def set_unit_color(self, code, color):
        """Plain-colour units change at once; textured ones are redrawn by the caller."""
        from PySide6.QtGui import QColor

        c = QColor(render.enhance(color) if self.look.get("vivid") else color)
        for key, a in self.units.items():
            if self.unit_code.get(key, key) == code:
                a.GetProperty().SetColor(c.redF(), c.greenF(), c.blueF())
        self.plotter.render()

    def set_ssao(self, on: bool):
        p = self.plotter
        try:
            if on:
                b = p.bounds
                span = max(b[1] - b[0], b[3] - b[2], b[5] - b[4]) or 1.0
                p.enable_ssao(radius=span * 0.03, bias=span * 0.0005, kernel_size=128, blur=True)
            else:
                p.disable_ssao()
        except Exception as e:  # noqa: BLE001
            self.message.emit(f"Ambient occlusion is not supported by this graphics driver ({e}).")
        p.render()

    def set_axes_grid(self, on: bool):
        self.show_axes_grid = on
        if self._model is not None:
            self._grid(self._model, self.ve)
        self.plotter.render()

    def show_terrain(self, dem, model, ve, margin=0.15, n=220, opacity=0.9):
        """The DEM around the model as a shaded, elevation-coloured surface."""
        if self._fs == 1.0:
            self._draws = [d for d in self._draws if d[0] != "show_terrain"]
            self._draws.append(("show_terrain", (dem, model, ve), dict(margin=margin, n=n, opacity=opacity)))
        from ..dem import sample_on_grid

        x0, x1, y0, y1 = model.x[0], model.x[-1], model.y[0], model.y[-1]
        dx, dy = (x1 - x0) * margin, (y1 - y0) * margin
        gx = np.linspace(x0 - dx, x1 + dx, n)
        gy = np.linspace(y0 - dy, y1 + dy, n)
        z = sample_on_grid(dem, gx, gy)
        if not np.isfinite(z).any():
            self.message.emit("The DEM does not cover the model area (check its coordinate system).")
            return False
        X, Y = np.meshgrid(gx, gy)
        # keep the terrain just outside the model so it does not hide the top of the solids
        inside = np.zeros_like(z, bool)
        if model.inside is not None:
            ix = np.clip(np.searchsorted(model.x, gx), 0, len(model.x) - 1)
            iy = np.clip(np.searchsorted(model.y, gy), 0, len(model.y) - 1)
            within = ((gx >= x0) & (gx <= x1))[None, :] & ((gy >= y0) & (gy <= y1))[:, None]
            inside = within & model.inside[np.ix_(iy, ix)]
        zz = np.where(inside, np.nan, z)
        grid = pv.StructuredGrid(X, Y, np.nan_to_num(z, nan=np.nanmin(z)) * ve)
        grid["Elevation (m)"] = z.ravel(order="F")
        grid["keep"] = np.isfinite(zz).ravel(order="F").astype(float)
        surf = grid.threshold(0.5, scalars="keep")
        self.extras["terrain"] = self.plotter.add_mesh(
            surf, scalars="Elevation (m)", cmap="gist_earth", opacity=opacity, smooth_shading=True,
            name="terrain", show_scalar_bar=True, specular=0.1,
            scalar_bar_args=dict(title="DEM elevation (m)", color=self._fg(), vertical=True, position_x=0.9,
                                 position_y=0.25, height=0.5, width=0.05, title_font_size=11, label_font_size=9))
        self._style_scalar_bars()
        self.plotter.render()
        return True

    def show_constraints(self, cons, model, ve):
        """Pinch-out lines (orange), absent areas (magenta outline) and thickness points (white) drawn on the
        ground surface of the model."""
        if self._fs == 1.0:
            self._draws = [d for d in self._draws if d[0] != "show_constraints"]
            self._draws.append(("show_constraints", (cons, model, ve), {}))

        colors = {"pinchout": "#FF8C1A", "absent": "#E040FB", "thickness": "#FFFFFF"}
        gz = np.nan_to_num(model.ground, nan=np.nanmean(model.ground))
        for k, c in enumerate(cons.items):
            xy = c.xy if c.kind != "absent" else np.vstack([c.xy, c.xy[:1]])
            ix = np.clip(np.searchsorted(model.x, xy[:, 0]), 0, len(model.x) - 1)
            iy = np.clip(np.searchsorted(model.y, xy[:, 1]), 0, len(model.y) - 1)
            z = gz[iy, ix] * ve + (model.x[-1] - model.x[0]) * 0.002
            pts = np.column_stack([xy, z])
            name = f"constraint_{k}"
            if c.kind == "thickness" or len(pts) == 1:
                self.extras[name] = self.plotter.add_mesh(pv.PolyData(pts), color=colors[c.kind],
                                                          point_size=10 * self._fs, render_points_as_spheres=True,
                                                          name=name)
            else:
                self.extras[name] = self.plotter.add_mesh(pv.lines_from_points(pts), color=colors[c.kind],
                                                          line_width=4 * self._fs, name=name)

    def _style_scalar_bars(self):
        for sb in list(getattr(self.plotter, "scalar_bars", {}).values()):
            try:
                render.style_text(sb.GetTitleTextProperty(), size=13 * self._ts, bold=True, color=self._fg())
                render.style_text(sb.GetLabelTextProperty(), size=11 * self._ts, color=self._fg(),
                                  weight="medium")
            except Exception:  # noqa: BLE001
                pass

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
        for a in list(self.units.values()) + [e for e in self.edges.values() if e is not None]:
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
            for a in list(self.units.values()) + [e for e in self.edges.values() if e is not None]:
                a.GetMapper().RemoveAllClippingPlanes()
            self._clip_plane = None
        try:
            self.plotter.clear_plane_widgets()
        except Exception:  # noqa: BLE001
            pass
        self.plotter.render()

    def _render_large(self, W: int, transparent=False, text_scale=None):
        """Rebuild the scene in an off-screen window W pixels wide, with fonts and line widths enlarged by
        the same factor, and render it once: text, labels, axes and lines keep their on-screen proportions
        and are drawn natively at print resolution (nothing is enlarged afterwards)."""
        src = self.plotter
        w, h = src.window_size
        H = max(1, round(W * h / max(w, 1)))
        cam = src.camera
        state = (cam.position, cam.focal_point, cam.up, cam.parallel_projection, cam.parallel_scale,
                 cam.view_angle)
        saved = {k: getattr(self, k) for k in ("units", "unit_code", "unit_hz", "edges", "extras", "_model",
                                               "ve", "_clip_plane")}
        off = pv.Plotter(off_screen=True, window_size=(W, H))
        try:
            if W * H <= 4500 * 3000:
                off.enable_anti_aliasing("msaa", multi_samples=4)
        except Exception:  # noqa: BLE001 - at print size aliasing is below one printed dot anyway
            pass
        try:
            self.plotter, self._fs = off, W / max(w, 1)
            self._ts = text_scale or self._fs
            self.units, self.unit_code, self.unit_hz, self.edges, self.extras = {}, {}, {}, {}, {}
            self._clip_plane = None
            bottom, top = self._bg_colors()
            off.set_background(bottom, top=top)
            for name, args, kw in self._draws:
                getattr(self, name)(*args, **kw)
            self._orientation_axes()
            self._apply_visibility(render=False)
            opac = saved["units"]
            for key, a in self.units.items():
                if key in opac:
                    a.GetProperty().SetOpacity(opac[key].GetProperty().GetOpacity())
            if self.look.get("ssao"):
                self.set_ssao(True)
            c = off.camera
            c.position, c.focal_point, c.up = state[0], state[1], state[2]
            c.parallel_projection, c.parallel_scale, c.view_angle = state[3], state[4], state[5]
            off.renderer.ResetCameraClippingRange()
            arr = off.screenshot(None, return_img=True, transparent_background=transparent)
        finally:
            self.plotter, self._fs, self._ts = src, 1.0, 1.0
            for k, v in saved.items():
                setattr(self, k, v)
            off.close()
            src.render()
        return arr

    def screenshot(self, path, scale: int = 3, transparent=False, legend=True):
        """Quick high-resolution image (window size × ``scale``)."""
        w = self.plotter.window_size[0]
        return self.export_image(path, w * scale, 300, legend=legend, transparent=transparent)

    # on-screen size (px) of the borehole labels; the export text size in points refers to these
    LABEL_PX = 13

    def export_image(self, path, width_px: int, dpi: int = 1000, legend=True, transparent=False,
                     text_pt: float | None = None):
        """Print-quality image ``width_px`` wide, tagged with ``dpi`` (e.g. 180 mm at 1000 dpi = 7087 px).

        The scene is rendered once more, off screen, at the full output size with fonts and line widths
        scaled to match, so text, labels and lines keep their proportions and stay sharp; the legend bar
        is drawn below it at the same scale.
        """
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None
        # text_pt: printed size of the labels in points (1 pt = 1/72 inch); axis text keeps its proportion
        ts = (text_pt / 72 * dpi) / self.LABEL_PX if text_pt else None
        img = Image.fromarray(self._render_large(int(width_px), transparent, ts))
        if legend and self.legend.isVisible() and self.legend.items:
            from PySide6.QtCore import QBuffer, QIODevice

            s = ts if ts else img.width / max(self.legend.width(), 1)
            q = self.legend.image(img.width, scale=s)
            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            q.save(buf, "PNG")
            import io

            leg = Image.open(io.BytesIO(bytes(buf.data()))).convert(img.mode)
            out = Image.new(img.mode, (img.width, img.height + leg.height))
            out.paste(img, (0, 0))
            out.paste(leg, (0, img.height))
            img = out
        if img.width != width_px:
            img = img.resize((int(width_px), round(img.height * width_px / img.width)), Image.LANCZOS)
        path = str(path)
        ext = path.lower().rsplit(".", 1)[-1]
        kw = {"dpi": (dpi, dpi)}
        if ext in ("tif", "tiff"):
            kw["compression"] = "tiff_lzw"
        elif ext in ("jpg", "jpeg"):
            img = img.convert("RGB")
            kw.update(quality=95, subsampling=0)
        img.save(path, **kw)
        return path
