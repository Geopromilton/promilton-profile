"""Start LithoLog Studio."""

from __future__ import annotations

import os
import sys


def main(argv=None):
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QSplashScreen

    from .. import __version__
    from . import theme

    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("LithoLog Studio")
    app.setOrganizationName("LithoLog")
    theme.apply(app, theme.saved_mode())
    from .logo import app_icon, pixmap

    app.setWindowIcon(app_icon())

    # Splash while VTK and the engine load.
    pm = QPixmap(660, 320)
    pm.fill(QColor(theme.BG))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.fillRect(0, 0, 8, 320, QColor(theme.ACCENT))
    p.drawPixmap(470, 70, pixmap(170))
    p.setPen(QColor(theme.TEXT))
    p.setFont(QFont("Segoe UI", 32, QFont.Bold))
    p.drawText(40, 125, "LithoLog")
    fm = p.fontMetrics()
    p.setPen(QColor(theme.ACCENT))
    p.drawText(40 + fm.horizontalAdvance("LithoLog "), 125, "Studio")
    p.setFont(QFont("Segoe UI", 11))
    p.setPen(QColor(theme.TEXT_DIM))
    p.drawText(42, 162, "Borehole logs · sections · maps · 3D geological models")
    p.drawText(42, 186, "Geology · hydrogeology · geochemistry · GIS")
    p.drawText(42, 285, f"Version {__version__} · open source (MIT)")
    p.end()
    splash = QSplashScreen(pm)
    splash.show()
    app.processEvents()

    from .mainwindow import MainWindow

    w = MainWindow()
    w.show()
    splash.finish(w)
    args = sys.argv[1:] if argv is None else argv[1:]
    if args:
        QTimer.singleShot(200, lambda: w.load(args[0]))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
