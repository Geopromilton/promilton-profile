"""LithoLog Studio look and feel: 'graphite' dark and 'daylight' light themes, amber accent.

The colour names below are module globals read at call time, so switching the
theme (``set_mode``) and re-applying the style sheet updates the whole UI.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

THEMES = {
    "dark": dict(ACCENT="#F0A43A", ACCENT_2="#4FA3E0", BG="#1B1F26", PANEL="#232830", PANEL_2="#2B313B",
                 BORDER="#363D48", TEXT="#E6E9EE", TEXT_DIM="#9AA3AF", SELECT="#3A3122", ALT="#262B34",
                 VIEW_BG_BOTTOM="#15181E", VIEW_BG_TOP="#3A4353", ON_ACCENT="#1B1F26"),
    "light": dict(ACCENT="#D9861C", ACCENT_2="#1F6FB2", BG="#EEF1F5", PANEL="#FFFFFF", PANEL_2="#F4F6F9",
                  BORDER="#D3D9E1", TEXT="#1E2530", TEXT_DIM="#5F6B7A", SELECT="#FBE7C8", ALT="#F7F8FA",
                  VIEW_BG_BOTTOM="#FFFFFF", VIEW_BG_TOP="#D5DEE9", ON_ACCENT="#FFFFFF"),
}
MODE = "dark"
ACCENT = ACCENT_2 = BG = PANEL = PANEL_2 = BORDER = TEXT = TEXT_DIM = SELECT = ALT = ""
VIEW_BG_BOTTOM = VIEW_BG_TOP = ON_ACCENT = ""


def set_mode(mode: str):
    global MODE
    MODE = mode if mode in THEMES else "dark"
    globals().update(THEMES[MODE])


set_mode("dark")


def qss() -> str:
    return f"""
* {{ font-family: 'Inter', 'Segoe UI', 'DejaVu Sans', sans-serif; font-size: 9.5pt; color: {TEXT}; }}
QMainWindow, QWidget {{ background: {BG}; }}
QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}

/* Ribbon */
#Ribbon {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
#Ribbon QTabBar::tab {{ background: transparent; color: {TEXT_DIM}; padding: 7px 18px; border: none;
                        font-weight: 600; letter-spacing: 0.5px; }}
#Ribbon QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
#Ribbon QTabBar::tab:hover {{ color: {TEXT}; }}
#Ribbon QTabWidget::pane {{ border: none; background: {PANEL}; }}
#RibbonPage {{ background: {PANEL}; }}
#RibbonGroup {{ background: transparent; border-right: 1px solid {BORDER}; }}
#RibbonGroupTitle {{ color: {TEXT_DIM}; font-size: 8pt; }}
#Ribbon QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px;
                       padding: 4px 8px; color: {TEXT}; font-size: 9pt; }}
#Ribbon QToolButton:hover {{ background: {PANEL_2}; border-color: {BORDER}; }}
#Ribbon QToolButton:pressed, #Ribbon QToolButton:checked {{ background: {SELECT}; border-color: {ACCENT}; }}
#AppBadge {{ color: {ACCENT}; font-size: 13pt; font-weight: 700; padding: 0 14px; }}

/* Docks */
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {PANEL}; padding: 6px 10px; border-bottom: 1px solid {BORDER};
                      font-weight: 600; color: {TEXT_DIM}; text-transform: uppercase; }}
QTreeWidget, QListWidget, QTableWidget, QTextEdit, QPlainTextEdit {{
    background: {PANEL}; border: none; alternate-background-color: {ALT}; }}
QTreeWidget::item, QListWidget::item {{ padding: 3px 2px; }}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{
    background: {SELECT}; color: {TEXT}; }}
QHeaderView::section {{ background: {PANEL_2}; color: {TEXT_DIM}; border: none; padding: 4px; }}

/* Document tabs */
#Documents::pane {{ border: none; border-top: 1px solid {BORDER}; }}
#Documents QTabBar::tab {{ background: {PANEL}; color: {TEXT_DIM}; padding: 7px 16px; border: 1px solid {BORDER};
                           border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;
                           margin-right: 2px; }}
#Documents QTabBar::tab:selected {{ background: {BG}; color: {TEXT}; border-top: 2px solid {ACCENT}; }}

/* Inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {PANEL_2}; border: 1px solid {BORDER};
    border-radius: 5px; padding: 4px 6px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {PANEL_2}; selection-background-color: {SELECT}; }}
QPushButton {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton#Primary {{ background: {ACCENT}; color: {ON_ACCENT}; border: none; font-weight: 700; }}
QPushButton#Primary:hover {{ background: {ACCENT_2}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 14px; padding: 10px 8px 8px 8px;
             background: {PANEL}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {ACCENT}; font-weight: 600; }}
QLabel#Dim {{ color: {TEXT_DIM}; }}
QLabel#H1 {{ font-size: 15pt; font-weight: 700; }}
QProgressBar {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 5px; text-align: center;
                height: 14px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; color: {TEXT_DIM}; }}
QScrollBar:vertical {{ background: {PANEL}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar:horizontal {{ background: {PANEL}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QMenu {{ background: {PANEL_2}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {SELECT}; }}
QSplitter::handle {{ background: {BORDER}; }}
"""


def apply(app, mode: str | None = None):
    if mode:
        set_mode(mode)
    from ..typeface import use_in_qt

    use_in_qt(app)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in [
        (QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, PANEL),
        (QPalette.AlternateBase, ALT), (QPalette.Text, TEXT), (QPalette.Button, PANEL_2),
        (QPalette.ButtonText, TEXT), (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, ON_ACCENT),
        (QPalette.ToolTipBase, PANEL_2), (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, TEXT_DIM),
    ]:
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(qss())


def icon(name: str, color: str | None = None, active: str | None = None):
    """Material Design icon (via qtawesome), e.g. icon('mdi6.cube-outline')."""
    import qtawesome as qta

    return qta.icon(name, color=color or TEXT, color_active=active or ACCENT)


def saved_mode() -> str:
    from PySide6.QtCore import QSettings

    return str(QSettings("LithoLog", "Studio").value("theme", "dark"))


def save_mode(mode: str):
    from PySide6.QtCore import QSettings

    QSettings("LithoLog", "Studio").setValue("theme", mode)
