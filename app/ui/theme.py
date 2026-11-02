from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from app import paths
from app.ui import fonts

# Design tokens. A dark theme later = another dict + another template.
COMMON = {
    "bg": "#F3F5F8", "panel": "#E9EDF2", "ribbon_bg": "#FFFFFF",
    "primary": "#2B6CB0", "primary_dark": "#1E4E80", "primary_light": "#3F85CC",
    "text": "#1F2933", "muted": "#6B7785", "border": "#D3D9E0",
    "hover": "#E6F0FA", "hover_border": "#B9D4EE", "pressed": "#CFE3F6",
}
# Nastaleeq glyphs are tall, so Urdu mode gets a bigger font and roomier controls.
PER_LANGUAGE = {
    "en": {"font_pt": 10, "small_pt": 8, "title_pt": 18, "tab_pad": "6px 14px", "file_pad": "6px 20px",
           "btn_pad": "3px 6px", "nav_pad": "10px 16px"},
    "ur": {"font_pt": 13, "small_pt": 10, "title_pt": 22, "tab_pad": "8px 16px", "file_pad": "8px 22px",
           "btn_pad": "4px 8px", "nav_pad": "12px 16px"},
}


def build_qss(lang: str) -> str:
    tokens = {**COMMON, **PER_LANGUAGE[lang]}
    text = (paths.assets_dir() / "themes" / "light.qss.tpl").read_text(encoding="utf-8")
    for name, value in tokens.items():
        text = text.replace("{{" + name + "}}", str(value))
    return text


def apply(app: QApplication, lang: str) -> None:
    font = QFont(fonts.family_for(lang))
    font.setPointSize(PER_LANGUAGE[lang]["font_pt"])
    app.setFont(font)
    app.setStyleSheet(build_qss(lang))
