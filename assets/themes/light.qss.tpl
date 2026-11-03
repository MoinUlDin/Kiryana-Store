/* Tokens look like {{name}} and are filled in by app/ui/theme.py */
QMainWindow, QWidget#Central { background: {{bg}}; }
QWidget { color: {{text}}; }

/* Quick access + header strip */
QWidget#QuickAccess { background: {{primary_dark}}; }
QWidget#QuickAccess QLabel { color: white; }
QWidget#QuickAccess QToolButton { background: transparent; border: none; border-radius: 3px; padding: 3px; }
QWidget#QuickAccess QToolButton:hover { background: {{primary}}; }
QWidget#RibbonHeader { background: {{primary}}; }

QToolButton#FileButton {
  background: {{primary_dark}}; color: white; border: none; padding: {{file_pad}}; font-weight: bold;
}
QToolButton#FileButton:hover { background: {{primary_light}}; }

QTabBar { background: transparent; }
QTabBar::tab { color: white; background: transparent; border: none; padding: {{tab_pad}}; margin: 0 2px; }
QTabBar::tab:hover:!selected { background: {{primary_light}}; }
QTabBar::tab:selected { background: {{ribbon_bg}}; color: {{primary_dark}}; border-top-left-radius: 4px; border-top-right-radius: 4px; }

/* Ribbon body */
QWidget#RibbonBody, QStackedWidget#RibbonBody { background: {{ribbon_bg}}; border-bottom: 1px solid {{border}}; }
QLabel#RibbonGroupTitle { color: {{muted}}; font-size: {{small_pt}}pt; }
QFrame#RibbonSep { background: {{border}}; border: none; min-width: 1px; max-width: 1px; }
QToolButton#RibbonButton { background: transparent; border: 1px solid transparent; border-radius: 4px; padding: {{btn_pad}}; }
QToolButton#RibbonButton:hover { background: {{hover}}; border-color: {{hover_border}}; }
QToolButton#RibbonButton:pressed { background: {{pressed}}; }
QToolButton#RibbonButton::menu-indicator { image: none; }

/* Content + status */
QLabel#Welcome { font-size: {{title_pt}}pt; color: {{muted}}; }
QStatusBar { background: {{panel}}; border-top: 1px solid {{border}}; }

/* Backstage */
QWidget#Backstage { background: white; }
QWidget#BackstageNav { background: {{primary_dark}}; }
QListWidget#BackstageList { background: transparent; border: none; color: white; outline: none; }
QListWidget#BackstageList::item { padding: {{nav_pad}}; }
QListWidget#BackstageList::item:hover { background: {{primary}}; }
QListWidget#BackstageList::item:selected { background: {{primary_light}}; color: white; }
QToolButton#BackstageBack, QPushButton#BackstageExit { background: transparent; color: white; border: none; padding: {{nav_pad}}; }
QToolButton#BackstageBack:hover, QPushButton#BackstageExit:hover { background: {{primary}}; }
QLabel#PageTitle { font-size: {{title_pt}}pt; font-weight: bold; color: {{primary_dark}}; }
QRadioButton { padding: 4px; }

QToolButton#RibbonCollapse { background: transparent; border: none; padding: 4px 10px; }
QToolButton#RibbonCollapse:hover { background: {{primary_light}}; }

/* Dialogs */
QDialog { background: white; }
QLabel#ErrorLabel { color: #B42318; }
QLineEdit, QComboBox { border: 1px solid {{border}}; border-radius: 4px; padding: 5px 8px; background: white; }
QLineEdit:focus, QComboBox:focus { border-color: {{primary}}; }
QPushButton { border: 1px solid {{border}}; border-radius: 4px; padding: 6px 16px; background: {{panel}}; }
QPushButton:hover { background: {{hover}}; }
QPushButton#PrimaryButton { background: {{primary}}; color: white; border-color: {{primary}}; }
QPushButton#PrimaryButton:hover { background: {{primary_light}}; }
QGroupBox { border: 1px solid {{border}}; border-radius: 4px; margin-top: 12px; padding-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }

QTableWidget { background: white; alternate-background-color: #F7F9FB; border: 1px solid {{border}}; gridline-color: {{border}}; }
QTableWidget::item:selected { background: {{hover}}; color: {{text}}; }
QHeaderView::section { background: {{panel}}; border: none; border-bottom: 1px solid {{border}}; padding: 6px 8px; font-weight: bold; }
QLabel#StatusNote { color: {{muted}}; }
