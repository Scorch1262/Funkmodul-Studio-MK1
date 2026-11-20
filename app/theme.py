"""Dunkles Dashboard-Design (Amber/Teal-Akzente) als Qt-Stylesheet."""

C = {
    "bg": "#0a0e13",
    "panel": "#10161e",
    "panel2": "#151d27",
    "panel3": "#1b2531",
    "border": "#233041",
    "border2": "#2e3d52",
    "text": "#d6dee8",
    "muted": "#7a889a",
    "dim": "#4f5d70",
    "amber": "#ffb020",
    "amber_dim": "#5a4313",
    "teal": "#1fd1c1",
    "teal_dim": "#0f4a46",
    "red": "#ff5f5f",
    "green": "#3ddc84",
    "violet": "#a98bff",
}

MONO = "'Cascadia Mono', 'Consolas', 'DejaVu Sans Mono', monospace"
SANS = "'Segoe UI', 'Inter', 'DejaVu Sans', sans-serif"

def build_qss(asset_dir: str) -> str:
    A = asset_dir.replace("\\", "/")
    return QSS_TEMPLATE.replace("@ASSETS@", A)


QSS_TEMPLATE = f"""
* {{
    font-family: {SANS};
    font-size: 10pt;
    color: {C['text']};
    outline: 0;
}}
QMainWindow, QDialog, QWidget#Root {{ background: {C['bg']}; }}
QWidget {{ background: transparent; }}
QToolTip {{ background: {C['panel3']}; color: {C['text']}; border: 1px solid {C['border2']}; padding: 4px; }}

/* ---------- Kopfzeile ---------- */
QFrame#TopBar {{ background: {C['panel']}; border-bottom: 1px solid {C['border']}; }}
QLabel#AppTitle {{ font-size: 12pt; font-weight: 700; letter-spacing: 3px; color: {C['text']}; }}
QLabel#AppSub {{ color: {C['muted']}; font-size: 8.5pt; letter-spacing: 1px; }}
QLabel#Pill {{
    border: 1px solid {C['border2']}; border-radius: 10px; padding: 2px 10px;
    font-size: 8.5pt; letter-spacing: 1px; color: {C['muted']}; background: {C['panel2']};
}}
QLabel#Pill[state="ok"] {{ color: {C['teal']}; border-color: {C['teal_dim']}; }}
QLabel#Pill[state="warn"] {{ color: {C['amber']}; border-color: {C['amber_dim']}; }}
QLabel#Pill[state="err"] {{ color: {C['red']}; border-color: #5a2323; }}

/* ---------- Seitenleiste ---------- */
QFrame#SideBar {{ background: {C['panel']}; border-right: 1px solid {C['border']}; }}
QPushButton#NavBtn {{
    text-align: left; padding: 10px 16px; border: none; border-left: 3px solid transparent;
    color: {C['muted']}; font-weight: 600; letter-spacing: 1px; border-radius: 0;
    background: transparent;
}}
QPushButton#NavBtn:hover {{ color: {C['text']}; background: {C['panel2']}; }}
QPushButton#NavBtn:checked {{ color: {C['amber']}; border-left: 3px solid {C['amber']}; background: {C['panel2']}; }}

/* ---------- Karten ---------- */
QFrame#Card {{ background: {C['panel']}; border: 1px solid {C['border']}; border-radius: 6px; }}
QLabel#CardTitle {{ color: {C['muted']}; font-size: 8.5pt; font-weight: 700; letter-spacing: 2px; }}
QLabel#Big {{ font-size: 16pt; font-weight: 700; color: {C['text']}; }}
QLabel#Muted {{ color: {C['muted']}; }}
QLabel#Accent {{ color: {C['amber']}; font-weight: 600; }}
QLabel#Teal {{ color: {C['teal']}; font-weight: 600; }}

/* ---------- Eingaben ---------- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {C['panel2']}; border: 1px solid {C['border']}; border-radius: 4px;
    padding: 5px 8px; selection-background-color: {C['teal_dim']}; selection-color: {C['text']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {C['teal']}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {C['dim']}; }}
QLineEdit#Payload {{ font-family: {MONO}; font-size: 10.5pt; padding: 7px 10px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: {C['panel3']}; }}
QSpinBox {{ padding-right: 20px; }}
QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; border-top-right-radius: 4px; }}
QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; border-bottom-right-radius: 4px; }}
QSpinBox::up-arrow {{ image: url(@ASSETS@/arrow_up.png); width: 10px; height: 10px; }}
QSpinBox::up-arrow:hover {{ image: url(@ASSETS@/arrow_up_hover.png); }}
QSpinBox::down-arrow {{ image: url(@ASSETS@/arrow_down.png); width: 10px; height: 10px; }}
QSpinBox::down-arrow:hover {{ image: url(@ASSETS@/arrow_down_hover.png); }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url(@ASSETS@/arrow_down.png); width: 12px; height: 12px; margin-right: 6px; }}
QComboBox::down-arrow:hover, QComboBox::down-arrow:on {{ image: url(@ASSETS@/arrow_down_hover.png); }}
QComboBox QAbstractItemView {{
    background: {C['panel2']}; border: 1px solid {C['border2']}; margin: 0; padding: 0;
    selection-background-color: {C['panel3']}; selection-color: {C['amber']};
}}
QComboBox QAbstractItemView::item {{ padding: 5px 8px; min-height: 20px; }}

/* ---------- Schaltflächen ---------- */
QPushButton {{
    background: {C['panel2']}; border: 1px solid {C['border2']}; border-radius: 4px;
    padding: 6px 14px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {C['teal']}; color: {C['teal']}; }}
QPushButton:pressed {{ background: {C['panel3']}; }}
QPushButton:disabled {{ color: {C['dim']}; border-color: {C['border']}; }}
QPushButton:checked {{ border-color: {C['teal']}; color: {C['teal']}; background: {C['teal_dim']}; }}
QPushButton#Primary {{ background: {C['amber']}; color: #1a1205; border: 1px solid {C['amber']}; }}
QPushButton#Primary:hover {{ background: #ffc24d; color: #1a1205; }}
QPushButton#Primary:disabled {{ background: {C['amber_dim']}; color: #8a7a5a; border-color: {C['amber_dim']}; }}
QPushButton#Danger {{ border-color: #5a2323; color: {C['red']}; }}
QPushButton#Danger:hover {{ background: #3a1616; color: {C['red']}; border-color: {C['red']}; }}
QPushButton#Chip {{
    border-radius: 12px; padding: 4px 12px; font-weight: 500; font-family: {MONO}; font-size: 9pt;
    background: {C['panel3']};
}}
QPushButton#Chip:hover {{ border-color: {C['amber']}; color: {C['amber']}; }}

QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {C['border2']}; border-radius: 3px; background: {C['panel2']}; }}
QCheckBox::indicator:checked {{ background: {C['teal']}; border-color: {C['teal']}; }}
QCheckBox:disabled {{ color: {C['dim']}; }}

/* ---------- Tabellen ---------- */
QTableWidget, QTableView, QListWidget {{
    background: {C['panel']}; alternate-background-color: {C['panel2']};
    border: 1px solid {C['border']}; border-radius: 4px; gridline-color: {C['border']};
    selection-background-color: {C['panel3']}; selection-color: {C['amber']};
}}
QTableWidget::item, QListWidget::item {{ padding: 4px 6px; border: none; }}
QHeaderView::section {{
    background: {C['panel2']}; color: {C['muted']}; border: none; border-bottom: 1px solid {C['border']};
    padding: 6px 8px; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px;
}}
QTableCornerButton::section {{ background: {C['panel2']}; border: none; }}

/* ---------- Log ---------- */
QPlainTextEdit#Log {{
    background: #070a0e; border: 1px solid {C['border']}; font-family: {MONO}; font-size: 9.5pt;
    padding: 6px;
}}

/* ---------- Scrollbalken ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['border2']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {C['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {C['border2']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSlider::groove:horizontal {{ height: 4px; background: {C['border2']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {C['teal']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {C['amber']}; width: 14px; margin: -6px 0; border-radius: 7px; }}

/* ---------- Hilfe ---------- */
QFrame#Help {{ background: #0e1620; border: 1px solid {C['teal_dim']}; border-left: 3px solid {C['teal']}; border-radius: 6px; }}
QLabel#HelpIcon {{ background: {C['teal_dim']}; color: {C['teal']}; border-radius: 11px; font-weight: 800; }}
QLabel#HelpTitle {{ color: {C['text']}; font-weight: 600; }}
QLabel#HelpDot {{ background: {C['panel3']}; color: {C['teal']}; border: 1px solid {C['teal_dim']}; border-radius: 8px; font-size: 8pt; font-weight: 800; }}
QPushButton#Link {{ background: transparent; border: none; color: {C['teal']}; padding: 2px 4px; font-weight: 500; }}
QPushButton#Link:hover {{ color: {C['amber']}; }}

/* ---------- Kacheln ---------- */
QFrame#Tile, QFrame#TileDanger {{ background: {C['panel2']}; border: 1px solid {C['border']}; border-radius: 6px; }}
QFrame#Tile:hover {{ border-color: {C['teal']}; background: {C['panel3']}; }}
QFrame#TileDanger {{ border-color: #4a2020; }}
QFrame#TileDanger:hover {{ border-color: {C['red']}; background: #241417; }}
QFrame#Tile[sel="true"], QFrame#TileDanger[sel="true"] {{ border: 2px solid {C['amber']}; background: #1f1a10; }}
QLabel#TileName {{ font-weight: 700; color: {C['text']}; }}
QLabel#TileCode {{ font-family: {MONO}; font-size: 8.5pt; color: {C['amber']}; }}
QLabel#TileDesc {{ color: {C['muted']}; font-size: 8.5pt; }}
QPushButton#GroupChip {{ border-radius: 13px; padding: 4px 14px; background: {C['panel2']}; font-weight: 600; }}
QPushButton#GroupChip:checked {{ background: {C['amber']}; color: #1a1205; border-color: {C['amber']}; }}

/* ---------- Kennzahlen / Schritte ---------- */
QFrame#Kpi {{ background: {C['panel2']}; border: 1px solid {C['border']}; border-radius: 6px; }}
QLabel#KpiTitle {{ color: {C['dim']}; font-size: 7.5pt; font-weight: 700; letter-spacing: 1px; }}
QLabel#KpiValue {{ font-size: 13pt; font-weight: 700; color: {C['text']}; }}
QLabel#Step {{ background: {C['panel3']}; border: 2px solid {C['border2']}; border-radius: 13px; color: {C['muted']}; font-weight: 800; }}
QLabel#Step[done="true"] {{ background: {C['teal_dim']}; border-color: {C['teal']}; color: {C['teal']}; }}
QFrame#StepBox {{ background: {C['panel2']}; border: 1px solid {C['border']}; border-radius: 6px; }}
QLabel#StepTitle {{ font-weight: 700; letter-spacing: 1px; font-size: 8.5pt; color: {C['muted']}; }}
QFrame#Analysis {{ background: #0b1118; border: 1px solid {C['border']}; border-radius: 6px; }}

QMenu {{ background: {C['panel2']}; border: 1px solid {C['border2']}; padding: 0; }}
QMenu::item {{ padding: 6px 18px; }}
QMenu::item:selected {{ background: {C['panel3']}; color: {C['amber']}; }}
QMessageBox {{ background: {C['panel']}; }}
QScrollArea {{ border: none; }}
"""

LOG_COLORS = {
    "info": C["muted"],
    "tx": C["amber"],
    "rx": C["teal"],
    "cmd_tx": C["violet"],
    "cmd_rx": C["violet"],
    "error": C["red"],
}
