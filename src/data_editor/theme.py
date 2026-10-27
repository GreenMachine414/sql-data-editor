"""Application colors. Neutral greys with a teal accent, in light and dark variants."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

LIGHT = {
    "accent": "#0f766e",
    "alternate": "#eef0f3",
    "selection": "#cdeae4",
    "selection_text": "#0b2b27",
    "hover": "#e9edf1",
    "accent_text": "#ffffff",
    "accent_hover": "#115e59",
}
DARK = {
    "accent": "#2dd4bf",
    "alternate": "#2a2d31",
    "selection": "#1f4d47",
    "selection_text": "#e6f4f1",
    "hover": "#34383d",
    "accent_text": "#0b2b27",
    "accent_hover": "#5eead4",
}


def is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    return hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark


def colors() -> dict:
    return DARK if is_dark() else LIGHT


def accent_color() -> QColor:
    return QColor(colors()["accent"])


def apply_theme(app) -> None:
    c = colors()
    palette = app.palette()
    palette.setColor(QPalette.AlternateBase, QColor(c["alternate"]))
    palette.setColor(QPalette.Highlight, QColor(c["selection"]))
    palette.setColor(QPalette.HighlightedText, QColor(c["selection_text"]))
    app.setPalette(palette)
    app.setStyleSheet(
        f"""
        QListWidget#tableList {{
            border: 1px solid palette(mid);
            border-radius: 4px;
            outline: 0;
        }}
        QListWidget#tableList::item {{
            padding: 5px 8px;
            border-radius: 4px;
        }}
        QListWidget#tableList::item:hover {{
            background: {c["hover"]};
        }}
        QListWidget#tableList::item:selected {{
            background: {c["selection"]};
            color: {c["selection_text"]};
            border-left: 3px solid {c["accent"]};
        }}
        QPushButton#primary {{
            background: {c["accent"]};
            color: {c["accent_text"]};
            border: 1px solid {c["accent"]};
            border-radius: 4px;
            padding: 6px 18px;
            font-weight: 600;
        }}
        QPushButton#primary:hover {{
            background: {c["accent_hover"]};
        }}
        QPushButton#primary:disabled {{
            background: palette(midlight);
            border-color: palette(mid);
            color: palette(mid);
        }}
        QTableView {{
            gridline-color: palette(midlight);
            alternate-background-color: {c["alternate"]};
            selection-background-color: {c["selection"]};
            selection-color: {c["selection_text"]};
        }}
        """
    )
