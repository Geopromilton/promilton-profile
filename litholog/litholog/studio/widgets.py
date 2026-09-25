"""Reusable Studio widgets: ribbon, 2D figure document, background worker."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy, QTabWidget, QToolButton,
                               QVBoxLayout, QWidget)

from . import theme


class Ribbon(QWidget):
    """Office-style ribbon: tabs of titled groups of large icon buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Ribbon")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        from .logo import pixmap

        badge = QWidget()
        bl = QHBoxLayout(badge)
        bl.setContentsMargins(12, 0, 10, 0)
        bl.setSpacing(6)
        mark = QLabel()
        mark.setPixmap(pixmap(26))
        name = QLabel("LithoLog Studio")
        name.setObjectName("AppBadge")
        bl.addWidget(mark)
        bl.addWidget(name)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("Ribbon")
        self.tabs.setCornerWidget(badge, Qt.TopLeftCorner)
        lay.addWidget(self.tabs)
        self.setFixedHeight(122)
        self.buttons = {}
        self._icons = {}

    def refresh_icons(self):
        """Re-colour the icons after a theme change."""
        for key, b in self.buttons.items():
            b.setIcon(theme.icon(self._icons[key]))

    def page(self, title: str) -> QWidget:
        w = QWidget()
        w.setObjectName("RibbonPage")
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 4, 6, 2)
        h.setSpacing(0)
        h.addStretch(1)
        self.tabs.addTab(w, title.upper())
        return w

    def group(self, page: QWidget, title: str, items):
        """items: [(key, icon_name, text, callback, checkable)]"""
        g = QFrame()
        g.setObjectName("RibbonGroup")
        v = QVBoxLayout(g)
        v.setContentsMargins(6, 2, 6, 2)
        v.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(2)
        for key, icon_name, text, cb, checkable in items:
            b = QToolButton()
            b.setIcon(theme.icon(icon_name))
            b.setIconSize(b.iconSize() * 1.6)
            b.setText(text)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(bool(checkable))
            b.setMinimumWidth(64)
            b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            if cb:
                b.clicked.connect(cb)
            row.addWidget(b)
            self.buttons[key] = b
            self._icons[key] = icon_name
        v.addLayout(row)
        t = QLabel(title)
        t.setObjectName("RibbonGroupTitle")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        lay = page.layout()
        lay.insertWidget(lay.count() - 1, g)
        return g


class FigureDoc(QWidget):
    """A matplotlib figure shown as a true-proportion page on a dark desk (like a PDF viewer)."""

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QScrollArea

        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(0)
        self.canvas = None
        self.toolbar = None
        self.figure = None
        self.zoom = 1.0
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet(f"QScrollArea {{ background: {theme.BG}; border: none; }}")
        self.scroll.setWidgetResizable(False)
        self.hint = QLabel(placeholder)
        self.hint.setObjectName("Dim")
        self.hint.setAlignment(Qt.AlignCenter)
        self.v.addWidget(self.hint)

    def set_figure(self, fig):
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

        if self.hint is not None:
            self.hint.setParent(None)
            self.hint = None
            self.v.addWidget(self.scroll, 1)
        if self.toolbar is not None:
            self.toolbar.setParent(None)
        self.figure = fig
        self.canvas = FigureCanvasQTAgg(fig)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.apply_theme()
        for text, factor in (("−", 1 / 1.25), ("+", 1.25), ("Fit", None)):
            b = QToolButton()
            b.setText(text)
            b.clicked.connect(lambda _=False, f=factor: self.set_zoom(f))
            self.toolbar.addWidget(b)
        self.v.insertWidget(0, self.toolbar)
        self.scroll.setWidget(self.canvas)
        self.set_zoom(None)

    def apply_theme(self):
        self.scroll.setStyleSheet(f"QScrollArea {{ background: {theme.BG}; border: none; }}")
        if self.toolbar is not None:
            self.toolbar.setStyleSheet(f"background: {theme.PANEL}; border-bottom: 1px solid {theme.BORDER};")

    def set_zoom(self, factor):
        """factor None = fit the whole page in the window."""
        if self.figure is None:
            return
        wi, hi = self.figure.get_size_inches()
        vw = max(self.scroll.viewport().width(), 400) - 24
        vh = max(self.scroll.viewport().height(), 300) - 24
        if factor is None:
            self.zoom = min(vw / wi, vh / hi) / 100.0
        else:
            self.zoom = min(max(self.zoom * factor, 0.2), 6.0)
        dpi = 100.0 * self.zoom
        self.figure.set_dpi(dpi)
        self.canvas.setFixedSize(int(wi * dpi), int(hi * dpi))
        self.canvas.draw_idle()

    def showEvent(self, e):  # fit once the widget has its real size
        super().showEvent(e)
        if self.figure is not None:
            self.set_zoom(None)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    """Run ``fn`` on a worker thread; emits done(result) or failed(message)."""

    def __init__(self, fn, *args, **kw):
        super().__init__()
        self.fn, self.args, self.kw = fn, args, kw
        self.signals = _Signals()

    def run(self):
        try:
            self.signals.done.emit(self.fn(*self.args, **self.kw))
        except Exception as e:  # noqa: BLE001 - reported in the UI
            self.signals.failed.emit(f"{e}\n\n{traceback.format_exc(limit=3)}")
