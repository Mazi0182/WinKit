"""
WinKit - GUI Stylesheet and Themes
Contains the unified dark theme QSS and color constants.
"""

DARK_THEME_PALETTE = {
    "bg_main": "#07090C",
    "bg_card": "#12161B",
    "bg_hover": "#241318",
    "border_subtle": "#2B333D",
    "border_focus": "#F04455",
    "accent": "#E63B4D",
    "accent_hover": "#FF6574",
    "text_primary": "#E9EDF2",
    "text_secondary": "#DCD2E2",
    "text_muted": "#8A94A0",
}

QSS = """
QMainWindow {
    background-color: #07090C;
}
QWidget#centralWidget {
    background-color: #07090C;
}
QFrame {
    border: none;
}
QPushButton {
    background-color: #12161B;
    color: #E9EDF2;
    border: 1px solid #2B333D;
    border-radius: 7px;
    padding: 8px 18px;
    font-family: "Segoe UI Variable Text";
    font-size: 13px;
}
QPushButton:hover {
    background-color: #241318;
    border: 1px solid #F04455;
    color: #FFFFFF;
}
QPushButton:pressed {
    background-color: #35161D;
}
QCheckBox {
    color: #DCD2E2;
    font-family: "Segoe UI Variable Text";
    font-size: 13px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #3B4652;
    border-radius: 4px;
    background-color: #11161B;
}
QCheckBox::indicator:checked {
    background-color: #E63B4D;
    border: 2px solid #FF6574;
}
QScrollBar:vertical {
    background: #0A0D11;
    width: 11px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #A82D3B;
    border-radius: 5px;
    min-height: 34px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QTextEdit {
    background-color: #06080A;
    color: #C9D1DA;
    border: 1px solid #27313A;
    border-radius: 7px;
    padding: 10px;
    font-family: "Consolas";
    font-size: 13px;
}
QLineEdit {
    background-color: #101419;
    color: #E9EDF2;
    border: 1px solid #303A45;
    border-radius: 6px;
    padding: 6px;
}
QLabel {
    color: #d0d0d5;
    background: transparent;
    background-color: transparent;
    border: none;
}
"""

# ---------- Hamburger Menu Button ----------
