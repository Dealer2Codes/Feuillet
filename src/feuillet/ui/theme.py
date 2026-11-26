"""Thème visuel de Feuillet : couleurs et feuille de style Qt (QSS).

Toutes les couleurs sont ici : l'interface ne code aucune couleur en dur
ailleurs que dans les icônes.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

PRIMARY = "#1D4ED8"  # boutons principaux, éléments actifs
PRIMARY_HOVER = "#1E40AF"
PRIMARY_SOFT = "#E8F0FE"
NAVY = "#0F2A6B"  # barre latérale (haut)
NAVY_2 = "#1E3A8A"  # barre latérale (bas), couleur du logo
TEAL = "#14B8A6"
DANGER = "#DC2626"
SUCCESS = "#16A34A"
SUCCESS_SOFT = "#DCFCE7"
WARNING_SOFT = "#FEF3C7"
BG = "#F3F6FB"
CARD = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT = "#0F172A"
MUTED = "#475569"
SUBTLE = "#64748B"

QSS = f"""
* {{ font-family: "Segoe UI", "Segoe UI Variable", Inter, sans-serif; color: {TEXT}; }}
QMainWindow, #Content {{ background: {BG}; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 6px 8px; border-radius: 6px; }}

/* ---------- barre latérale ---------- */
#Sidebar {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {NAVY}, stop:1 {NAVY_2}); }}
#Sidebar QPushButton {{
    color: #DCE6FF; background: transparent; border: none; border-radius: 10px;
    text-align: left; padding: 10px 14px; font-size: 15px;
}}
#Sidebar QPushButton:hover {{ background: rgba(255,255,255,0.10); color: white; }}
#Sidebar QPushButton:checked {{ background: {PRIMARY}; color: white; font-weight: 600; }}
#SidebarSeparator {{ background: rgba(255,255,255,0.18); max-height: 1px; min-height: 1px; }}
#OfflineBadge {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.18); border-radius: 12px; }}
#OfflineBadge QLabel {{ color: white; background: transparent; }}
#OfflineBadge #BadgeSub {{ color: #C7D5F5; font-size: 12px; }}

/* ---------- en-tête ---------- */
#Header {{ background: {CARD}; border-bottom: 1px solid {BORDER}; }}
#AppName {{ font-size: 30px; font-weight: 800; color: {NAVY_2}; }}
#AppTagline {{ font-size: 14px; color: {MUTED}; }}
#PrivacyBanner {{ background: {PRIMARY_SOFT}; border: 1px solid #C9DAFB; border-radius: 14px; }}
#PrivacyBanner QLabel {{ background: transparent; }}
#PrivacyTitle {{ font-size: 14px; font-weight: 700; }}
#PrivacySub {{ font-size: 12px; color: {MUTED}; }}

/* ---------- cartes ---------- */
#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}
#Card QLabel {{ background: transparent; }}
#CardTitle {{ font-size: 16px; font-weight: 700; }}
#SoftCard {{ background: {PRIMARY_SOFT}; border: 1px solid #C9DAFB; border-radius: 14px; }}
#SoftCard QLabel {{ background: transparent; }}
#TipCard {{ background: #FFF8E6; border: 1px solid #FBE3A6; border-radius: 14px; }}
#TipCard QLabel {{ background: transparent; }}
#Muted {{ color: {MUTED}; }}
#PageTitle {{ font-size: 22px; font-weight: 800; }}
#PageSub {{ color: {MUTED}; font-size: 14px; }}

QGroupBox {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px;
    margin-top: 14px; padding: 18px 14px 12px 14px; font-size: 15px; font-weight: 700;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; top: 2px; padding: 0 4px; background: transparent; }}

/* ---------- cartes de mode (onglets du haut) ---------- */
#ModeCard {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; text-align: left; padding: 12px 16px;
}}
#ModeCard:hover {{ border-color: #93B4F5; }}
#ModeCard:checked {{ background: {PRIMARY}; border-color: {PRIMARY}; }}
#ModeCard QLabel {{ background: transparent; }}
#ModeTitle {{ font-size: 16px; font-weight: 700; }}
#ModeSub {{ font-size: 12px; color: {MUTED}; }}

/* ---------- boutons ---------- */
QPushButton {{
    background: {CARD}; border: 1px solid #CBD5E1; border-radius: 8px; padding: 7px 14px; font-size: 14px;
}}
QPushButton:hover {{ border-color: #93B4F5; background: #F8FAFF; }}
QPushButton:pressed {{ background: {PRIMARY_SOFT}; }}
QPushButton:disabled {{ color: #94A3B8; background: #F1F5F9; border-color: #E2E8F0; }}
#SuccessBadge {{ background: {SUCCESS_SOFT}; border-radius: 28px; }}
#SuccessTitle {{ font-size: 17px; font-weight: 700; color: {TEXT}; }}
#SuccessFiles {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 10px; color: {MUTED}; }}
#PageScroll, #PageScroll > QWidget > QWidget {{ background: transparent; }}
QPushButton#IconAction {{ padding: 0; border-radius: 10px; }}
QPushButton#IconAction:hover {{ background: {PRIMARY_SOFT}; border-color: {PRIMARY}; }}
QPushButton#Primary {{ background: {PRIMARY}; color: white; border: none; font-weight: 700; padding: 10px 18px; }}
QPushButton#Primary:hover {{ background: {PRIMARY_HOVER}; }}
QPushButton#Primary:disabled {{ background: #A5B8E8; color: #EEF2FF; }}
QPushButton#Big {{ font-size: 16px; padding: 12px 18px; border-radius: 10px; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton:hover {{ background: #EEF2F7; }}
QToolButton:checked {{ background: {PRIMARY_SOFT}; }}

/* ---------- champs ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {CARD}; border: 1px solid #CBD5E1; border-radius: 8px; padding: 6px 10px; min-height: 22px;
    selection-background-color: {PRIMARY};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {PRIMARY}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; border: none; background: transparent;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; margin: 3px 3px 0 0; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0 3px 3px 0; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: #EEF2F7; border-radius: 4px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ width: 8px; height: 8px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ width: 8px; height: 8px; }}
QComboBox QAbstractItemView {{ border: 1px solid {BORDER}; selection-background-color: {PRIMARY_SOFT}; selection-color: {TEXT}; }}
QSlider::groove:horizontal {{ height: 4px; background: #E2E8F0; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {PRIMARY}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; border: 2px solid {PRIMARY}; width: 14px; height: 14px; margin: -7px 0; border-radius: 9px; }}
QProgressBar {{ background: #E2E8F0; border: none; border-radius: 4px; max-height: 8px; }}
QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 4px; }}

/* ---------- listes ---------- */
QListWidget, QTreeWidget {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: 4px; }}
QListWidget::item, QTreeWidget::item {{ border-radius: 6px; padding: 4px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {PRIMARY_SOFT}; color: {TEXT}; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: #F1F5F9; }}
QTreeWidget#ToolTree {{ show-decoration-selected: 0; }}
QTreeWidget#ToolTree::item {{ padding: 3px 6px; margin: 1px 0; }}
QTreeWidget#ToolTree::item:selected {{ background: {SUCCESS_SOFT}; color: #166534; font-weight: 600;
    border-left: 3px solid {SUCCESS}; }}
QTreeWidget#ToolTree::item:hover:!selected {{ background: #F0FDF4; }}
QTreeWidget#ToolTree::branch, QTreeWidget#ToolTree::branch:selected,
QTreeWidget#ToolTree::branch:hover {{ background: {CARD}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #CBD5E1; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #CBD5E1; border-radius: 4px; min-width: 30px; }}

/* ---------- zone de dépôt ---------- */
#DropZone {{ background: #F8FBFF; border: 2px dashed #A9C1F5; border-radius: 12px; }}
#DropZone[hover="true"] {{ background: {PRIMARY_SOFT}; border-color: {PRIMARY}; }}
#DropZone QLabel {{ background: transparent; }}

/* ---------- aperçu ---------- */
#PreviewToolbar {{ background: #F8FAFC; border-bottom: 1px solid {BORDER}; border-top-left-radius: 14px; border-top-right-radius: 14px; }}
#PreviewCanvas {{ background: #E9EEF5; }}
#PreviewFooter {{ background: #F8FAFC; border-top: 1px solid {BORDER}; border-bottom-left-radius: 14px; border-bottom-right-radius: 14px; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")  # base identique sur toutes les versions de Windows
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.Base, QColor(CARD))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(PRIMARY))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(SUBTLE))
    app.setPalette(palette)
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    app.setStyleSheet(QSS)
