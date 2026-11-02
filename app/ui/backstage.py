from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QPushButton, QRadioButton, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from app import __version__
from app.ui.glyphs import glyph_icon
from app.ui.i18n.catalog import LANGUAGES
from app.ui.i18n.manager import I18n

# (key, phase in which the real page is built; None = built now)
PAGES = (("backup", 8), ("users", 1), ("license", 9), ("language", None), ("about", None))


class BackstageView(QWidget):
    """Full-window File menu. Covers the ribbon and content until the user goes back."""

    closed = pyqtSignal()
    exit_requested = pyqtSignal()
    sign_out_requested = pyqtSignal()

    def __init__(self, i18n: I18n, parent: QWidget) -> None:
        super().__init__(parent)
        self._i18n = i18n
        self.setObjectName("Backstage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        nav = QWidget(self)
        nav.setObjectName("BackstageNav")
        nav.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        nav.setFixedWidth(240)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        self._back = QToolButton(nav)
        self._back.setObjectName("BackstageBack")
        self._back.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._back.clicked.connect(self.close_view)
        nav_layout.addWidget(self._back)
        self._list = QListWidget(nav)
        self._list.setObjectName("BackstageList")
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        nav_layout.addWidget(self._list, 1)
        self._signout = QPushButton(nav)
        self._signout.setObjectName("BackstageExit")
        self._signout.clicked.connect(self.sign_out_requested)
        nav_layout.addWidget(self._signout)
        self._exit = QPushButton(nav)
        self._exit.setObjectName("BackstageExit")
        self._exit.clicked.connect(self.exit_requested)
        nav_layout.addWidget(self._exit)
        root.addWidget(nav)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack, 1)

        self._titles: dict[str, QLabel] = {}
        self._placeholders: dict[str, QLabel] = {}
        for key, phase in PAGES:
            self._list.addItem("")
            self._stack.addWidget(self._build_page(key, phase))
        self._list.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._list.setCurrentRow(0)

        self.retranslate()

    # ---- pages --------------------------------------------------------
    def _build_page(self, key: str, phase: int | None) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(14)
        title = QLabel(page)
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        self._titles[key] = title

        if key == "language":
            self._note = QLabel(page)
            layout.addWidget(self._note)
            self._radios: dict[str, QRadioButton] = {}
            for code, info in LANGUAGES.items():
                radio = QRadioButton(info.native_name, page)  # always shown in its own language
                radio.toggled.connect(lambda checked, c=code: checked and self._i18n.set_language(c))
                layout.addWidget(radio)
                self._radios[code] = radio
            self.sync_language_radios()
        elif key == "about":
            self._about = QLabel(page)
            layout.addWidget(self._about)
        else:
            label = QLabel(page)
            layout.addWidget(label)
            self._placeholders[key] = label
        layout.addStretch(1)
        return page

    def sync_language_radios(self) -> None:
        for code, radio in self._radios.items():
            radio.blockSignals(True)
            radio.setChecked(code == self._i18n.lang)
            radio.blockSignals(False)

    # ---- behaviour ----------------------------------------------------
    def open_view(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()

    def close_view(self) -> None:
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_view()
        else:
            super().keyPressEvent(event)

    def retranslate(self) -> None:
        tr = self._i18n.tr
        rtl = self._i18n.is_rtl
        self._back.setText(tr("backstage.back"))
        self._back.setIcon(glyph_icon("\uE72A" if rtl else "\uE72B", 16, "#FFFFFF"))  # forward / back arrow
        self._signout.setText(tr("backstage.signout"))
        self._exit.setText(tr("backstage.exit"))
        for row, (key, phase) in enumerate(PAGES):
            text = tr(f"backstage.{key}")
            self._list.item(row).setText(text)
            self._titles[key].setText(text)
            if key in self._placeholders:
                self._placeholders[key].setText(tr("backstage.placeholder", phase=phase))
        self._note.setText(tr("backstage.language.note"))
        self._about.setText(tr("backstage.about.text", version=__version__))
        self._titles["language"].setText(tr("backstage.language.title"))
        self.sync_language_radios()
