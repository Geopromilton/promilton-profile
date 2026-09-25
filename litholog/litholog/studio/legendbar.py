"""Horizontal, editable legend under the 3D view, and the Layer Properties dialog."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QSlider, QVBoxLayout, QWidget)

from . import theme


class LegendBar(QWidget):
    """Chips (swatch · name · volume) laid out left to right, wrapping to new rows.

    Click a chip to edit the layer, right-click for hide/show and options,
    double-click the title to rename the legend.
    """

    edit_requested = Signal(str)
    visibility_changed = Signal(str, bool)

    PAD, GAP, ROW_H, SW_W, SW_H = 10, 18, 24, 30, 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[dict] = []   # code, name, color, volume (MCM or None), visible
        self.title = "Lithology"
        self.show_volumes = True
        self.subtitle = ""
        self._hits: list[tuple[QRectF, str]] = []
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.hide()

    # ------------------------------------------------------------------ data
    def set_items(self, items, subtitle: str = ""):
        self.items = list(items)
        self.subtitle = subtitle
        self.setVisible(bool(self.items) and getattr(self, "_enabled", True))
        self.updateGeometry()
        self.update()

    def set_enabled_bar(self, on: bool):
        self._enabled = on
        self.setVisible(on and bool(self.items))

    def set_visible_code(self, code, visible):
        for it in self.items:
            if it["code"] == code:
                it["visible"] = visible
        self.update()

    # ------------------------------------------------------------------ layout / paint
    def _label(self, it):
        v = it.get("volume")
        return it["name"] + (f"  ·  {v:,.1f} MCM" if self.show_volumes and v is not None else "")

    def _layout(self, width: float, s: float = 1.0):
        f = QFont(self.font())
        f.setPointSizeF(9 * s if s != 1 else 9)
        fb = QFont(f)
        fb.setBold(True)
        fm, fmb = QFontMetrics(f), QFontMetrics(fb)
        pad, gap, row_h, sw_w = self.PAD * s, self.GAP * s, self.ROW_H * s, self.SW_W * s
        x = pad + fmb.horizontalAdvance(self.title.upper()) + gap
        x0 = x
        y = pad * 0.6
        rects = []
        for it in self.items:
            w = sw_w + 7 * s + fm.horizontalAdvance(self._label(it))
            if x + w > width - pad and x > x0:
                x, y = x0, y + row_h
            rects.append((QRectF(x, y, w, row_h), it))
            x += w + gap
        total_h = y + row_h + pad * 0.6
        if self.subtitle:
            total_h += row_h * 0.8
        return rects, total_h, f, fb

    def sizeHint(self):
        _, h, _, _ = self._layout(max(self.width(), 600))
        return QSize(600, int(h))

    def minimumSizeHint(self):
        return self.sizeHint()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return int(self._layout(w)[1])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = self.heightForWidth(self.width())
        if self.height() != h:
            self.setFixedHeight(h)

    def paint(self, p: QPainter, width: float, s: float = 1.0, bg=None):
        rects, h, f, fb = self._layout(width, s)
        p.fillRect(QRectF(0, 0, width, h), QColor(bg or theme.PANEL))
        p.setPen(QPen(QColor(theme.BORDER), max(1.0, s)))
        p.drawLine(0, 0, int(width), 0)
        p.setFont(fb)
        p.setPen(QColor(theme.ACCENT))
        p.drawText(QRectF(self.PAD * s, self.PAD * 0.6 * s, width, self.ROW_H * s), Qt.AlignVCenter,
                   self.title.upper())
        p.setFont(f)
        hits = []
        for r, it in rects:
            alpha = 255 if it.get("visible", True) else 80
            sw = QRectF(r.x(), r.y() + (r.height() - self.SW_H * s) / 2, self.SW_W * s, self.SW_H * s)
            c = QColor(it["color"])
            c.setAlpha(alpha)
            p.setBrush(c)
            p.setPen(QPen(QColor(theme.BORDER), max(1.0, s)))
            p.drawRoundedRect(sw, 3 * s, 3 * s)
            t = QColor(theme.TEXT)
            t.setAlpha(alpha)
            p.setPen(t)
            tr = QRectF(sw.right() + 7 * s, r.y(), r.width() - sw.width() - 7 * s, r.height())
            p.drawText(tr, Qt.AlignVCenter | Qt.AlignLeft, self._label(it))
            if not it.get("visible", True):
                p.drawLine(tr.left(), tr.center().y(), tr.right(), tr.center().y())
            hits.append((r, it["code"]))
        if self.subtitle:
            p.setPen(QColor(theme.TEXT_DIM))
            ff = QFont(f)
            ff.setPointSizeF(f.pointSizeF() * 0.85)
            p.setFont(ff)
            p.drawText(QRectF(self.PAD * s, h - self.ROW_H * 0.8 * s - self.PAD * 0.4 * s, width - 2 * self.PAD * s,
                              self.ROW_H * 0.8 * s), Qt.AlignVCenter | Qt.AlignLeft, self.subtitle)
        return hits

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._hits = self.paint(p, self.width())
        p.end()

    def image(self, width: int, scale: float = 1.0) -> QImage:
        """The legend rendered at ``width`` pixels (for composing with screenshots)."""
        _, h, _, _ = self._layout(width, scale)
        img = QImage(int(width), int(h), QImage.Format_ARGB32)
        img.fill(QColor(theme.PANEL))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self.paint(p, width, scale)
        p.end()
        return img

    # ------------------------------------------------------------------ interaction
    def _code_at(self, pos):
        for r, code in self._hits:
            if r.contains(pos):
                return code
        return None

    def mouseReleaseEvent(self, e):
        code = self._code_at(e.position())
        if e.button() == Qt.LeftButton and code:
            self.edit_requested.emit(code)

    def mouseDoubleClickEvent(self, e):
        if self._code_at(e.position()) is None:
            self.edit_title()

    def contextMenuEvent(self, e):
        code = self._code_at(e.pos())
        m = QMenu(self)
        if code:
            it = next(i for i in self.items if i["code"] == code)
            m.addAction(theme.icon("mdi6.palette-outline"), f"Layer properties: {it['name']}…",
                        lambda: self.edit_requested.emit(code))
            vis = it.get("visible", True)
            m.addAction(theme.icon("mdi6.eye-off-outline" if vis else "mdi6.eye-outline"),
                        "Hide layer" if vis else "Show layer", lambda: self._toggle(code, not vis))
            m.addAction("Show only this layer", lambda: self._only(code))
        m.addAction("Show all layers", self._show_all)
        m.addSeparator()
        a = m.addAction("Show volumes")
        a.setCheckable(True)
        a.setChecked(self.show_volumes)
        a.toggled.connect(self._set_volumes)
        m.addAction("Rename legend…", self.edit_title)
        m.exec(e.globalPos())

    def _toggle(self, code, vis):
        self.set_visible_code(code, vis)
        self.visibility_changed.emit(code, vis)

    def _only(self, code):
        for it in self.items:
            self._toggle(it["code"], it["code"] == code)

    def _show_all(self):
        for it in self.items:
            self._toggle(it["code"], True)

    def _set_volumes(self, on):
        self.show_volumes = on
        self.setFixedHeight(self.heightForWidth(self.width()))
        self.update()

    def edit_title(self):
        t, ok = QInputDialog.getText(self, "Legend", "Legend title:", text=self.title)
        if ok and t.strip():
            self.title = t.strip()
            self.update()


# ---------------------------------------------------------------------------
def pattern_preview(lith, w=150, h=64) -> QPixmap:
    """The 2D fill pattern as it prints on logs and sections."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from ..patterns import draw_interval

    fig = Figure(figsize=(w / 100, h / 100), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(1, 0)
    ax.set_axis_off()
    draw_interval(ax, 0, 1, 0, 1, lith)
    fig.canvas.draw()
    buf = fig.canvas.buffer_rgba()
    img = QImage(bytes(buf), int(fig.bbox.width), int(fig.bbox.height), QImage.Format_RGBA8888)
    return QPixmap.fromImage(img.copy())


class LayerPropertiesDialog(QDialog):
    """Name, colour, pattern and 3D display of every layer; saves/loads legend files."""

    def __init__(self, legend, codes, state, current=None, volumes=None, parent=None):
        super().__init__(parent)
        from ..patterns import LithType, PATTERNS

        self.LithType = LithType
        self.setWindowTitle("Layer properties")
        self.resize(760, 480)
        self.legend = legend
        self.codes = list(codes)
        self.volumes = volumes or {}
        self.edits = {c: dict(name=legend.get(c).name, color=legend.get(c).color, pattern=legend.get(c).pattern,
                              group=legend.get(c).group, visible=state.get(c, {}).get("visible", True),
                              opacity=state.get(c, {}).get("opacity", 1.0)) for c in self.codes}
        self.loaded_legend = None

        root = QHBoxLayout(self)
        self.list = QListWidget()
        self.list.setMinimumWidth(240)
        self.list.setMaximumWidth(320)
        root.addWidget(self.list)
        right = QVBoxLayout()
        root.addLayout(right, 1)
        f = QFormLayout()
        self.code_lbl = QLabel()
        self.name = QLineEdit()
        self.color_btn = QPushButton()
        self.color_btn.setMinimumHeight(30)
        self.pattern = QComboBox()
        self.pattern.setEditable(True)
        self.pattern.addItems(list(PATTERNS))
        self.pattern.setToolTip("Combine patterns with +, e.g. waves+fractures")
        self.group = QLineEdit()
        self.visible = QCheckBox("Show in 3D view")
        self.opacity = QSlider(Qt.Horizontal, minimum=5, maximum=100)
        self.vol_lbl = QLabel()
        self.vol_lbl.setObjectName("Dim")
        f.addRow("Code", self.code_lbl)
        f.addRow("Name", self.name)
        f.addRow("Colour", self.color_btn)
        f.addRow("Pattern (2D)", self.pattern)
        f.addRow("Group", self.group)
        f.addRow("", self.visible)
        f.addRow("Opacity (3D)", self.opacity)
        f.addRow("Volume", self.vol_lbl)
        right.addLayout(f)
        self.preview = QLabel()
        self.preview.setMinimumHeight(70)
        right.addWidget(QLabel("Preview (logs and sections):"))
        right.addWidget(self.preview)
        right.addStretch(1)
        io = QHBoxLayout()
        b_save = QPushButton(theme.icon("mdi6.content-save-outline"), " Save legend…")
        b_load = QPushButton(theme.icon("mdi6.folder-open-outline"), " Load legend…")
        b_save.clicked.connect(self.save_legend)
        b_load.clicked.connect(self.load_legend)
        io.addWidget(b_save)
        io.addWidget(b_load)
        io.addStretch(1)
        right.addLayout(io)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.apply_btn = bb.button(QDialogButtonBox.Apply)
        right.addWidget(bb)

        for c in self.codes:
            it = QListWidgetItem(self._icon(self.edits[c]["color"]), self.edits[c]["name"])
            it.setData(Qt.UserRole, c)
            self.list.addItem(it)
        self.list.currentRowChanged.connect(self._show)
        self.name.textEdited.connect(lambda t: self._set("name", t))
        self.pattern.currentTextChanged.connect(lambda t: self._set("pattern", t))
        self.group.textEdited.connect(lambda t: self._set("group", t))
        self.visible.toggled.connect(lambda v: self._set("visible", v))
        self.opacity.valueChanged.connect(lambda v: self._set("opacity", v / 100))
        self.color_btn.clicked.connect(self._pick_color)
        self._cur = None
        self.list.setCurrentRow(self.codes.index(current) if current in self.codes else 0)

    @staticmethod
    def _icon(color):
        pm = QPixmap(16, 16)
        pm.fill(QColor(color))
        return pm

    def _show(self, row):
        if row < 0:
            return
        c = self._cur = self.codes[row]
        e = self.edits[c]
        for w in (self.name, self.pattern, self.group, self.visible, self.opacity):
            w.blockSignals(True)
        self.code_lbl.setText(c)
        self.name.setText(e["name"])
        self.pattern.setCurrentText(e["pattern"])
        self.group.setText(e["group"])
        self.visible.setChecked(e["visible"])
        self.opacity.setValue(int(round(e["opacity"] * 100)))
        for w in (self.name, self.pattern, self.group, self.visible, self.opacity):
            w.blockSignals(False)
        v = self.volumes.get(c)
        self.vol_lbl.setText(f"{v:,.2f} MCM (million m³)" if v is not None else "—")
        self._refresh()

    def _set(self, key, value):
        if self._cur is None:
            return
        self.edits[self._cur][key] = value
        if key in ("name", "color", "pattern"):
            self._refresh()

    def _refresh(self):
        e = self.edits[self._cur]
        self.color_btn.setText(e["color"].upper())
        fg = "#1B1F26" if QColor(e["color"]).lightnessF() > 0.55 else "#FFFFFF"
        self.color_btn.setStyleSheet(f"background: {e['color']}; color: {fg}; font-weight: 600;")
        it = self.list.item(self.codes.index(self._cur))
        it.setText(e["name"])
        it.setIcon(self._icon(e["color"]))
        try:
            self.preview.setPixmap(pattern_preview(self.LithType(self._cur, e["name"], e["color"], e["pattern"]),
                                                   320, 64))
        except Exception:  # noqa: BLE001 - unknown pattern name while typing
            pass

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.edits[self._cur]["color"]), self, "Layer colour")
        if c.isValid():
            self._set("color", c.name())

    def rows(self):
        return [dict(code=c, **{k: v for k, v in e.items() if k in ("name", "color", "pattern", "group")})
                for c, e in self.edits.items()]

    def save_legend(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save legend", "legend.csv", "CSV (*.csv)")
        if path:
            from ..io import save_legend

            save_legend(self.legend.updated(self.rows()), path, self.codes)

    def load_legend(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load legend", "", "Legend (*.csv *.xlsx)")
        if not path:
            return
        from ..io import load_legend

        lg = load_legend(path, self.legend)
        for c in self.codes:
            t = lg.get(c)
            self.edits[c].update(name=t.name, color=t.color, pattern=t.pattern, group=t.group)
        self._show(self.list.currentRow())
