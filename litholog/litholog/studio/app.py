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
    theme.apply(app)

    # Splash while VTK and the engine load.
    pm = QPixmap(620, 300)
    pm.fill(QColor(theme.BG))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.fillRect(0, 0, 8, 300, QColor(theme.ACCENT))
    for i, col in enumerate(["#A67C52", "#E8C9A6", "#D9CFEA", "#9FCBEA", "#C7A49B"]):
        p.fillRect(470, 60 + i * 34, 110, 30, QColor(col))
    p.setPen(QColor(theme.TEXT))
    f = QFont("Segoe UI", 30, QFont.Bold)
    p.setFont(f)
    p.drawText(40, 120, "LithoLog Studio")
    p.setFont(QFont("Segoe UI", 11))
    p.setPen(QColor(theme.TEXT_DIM))
    p.drawText(42, 155, "Borehole logs · sections · maps · 3D lithology models")
    p.drawText(42, 260, f"Version {__version__} · open source")
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
