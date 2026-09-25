"""LithoLog's typeface: Inter (SIL Open Font License, bundled in litholog/fonts).

Registered for matplotlib (logs, sections, maps, diagrams), Qt (Studio) and VTK
(3D labels), with DejaVu Sans as the fallback.
"""

from __future__ import annotations

from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FAMILY = "Inter"
FILES = {"regular": "Inter-Regular.ttf", "medium": "Inter-Medium.ttf", "semibold": "Inter-SemiBold.ttf",
         "bold": "Inter-Bold.ttf", "italic": "Inter-Italic.ttf"}
_done = {"mpl": False}


def path(weight: str = "regular") -> str:
    return str(FONT_DIR / FILES.get(weight, FILES["regular"]))


def available() -> bool:
    return (FONT_DIR / FILES["regular"]).exists()


def use_in_matplotlib():
    """Make Inter the default matplotlib font (once)."""
    if _done["mpl"] or not available():
        return
    from matplotlib import font_manager, rcParams

    for f in FILES.values():
        p = FONT_DIR / f
        if p.exists():
            font_manager.fontManager.addfont(str(p))
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = [FAMILY, "DejaVu Sans", "Arial", "sans-serif"]
    rcParams["mathtext.fontset"] = "dejavusans"
    _done["mpl"] = True


def use_in_qt(app, size: float = 9.5):
    """Register the font files with Qt and make Inter the application font."""
    from PySide6.QtGui import QFont, QFontDatabase

    if available():
        for f in FILES.values():
            QFontDatabase.addApplicationFont(str(FONT_DIR / f))
    font = QFont(FAMILY if available() else "Segoe UI")
    font.setPointSizeF(size)
    font.setHintingPreference(QFont.PreferNoHinting)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    return font
