"""Kiryana POS entry point."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from app import paths
from app.db.connection import connect
from app.db.migrator import migrate
from app.infra.logging_setup import setup_logging
from app.repositories.settings_repo import SettingsRepo
from app.ui.i18n.catalog import DEFAULT_LANGUAGE, Catalog

I18N_DIR = Path(__file__).resolve().parent / "app" / "ui" / "i18n"


def main() -> int:
    paths.ensure_dirs()
    setup_logging()
    log = logging.getLogger("main")

    conn = connect(paths.db_path())
    try:
        log.info("database ready at schema version %s", migrate(conn, backup_dir=paths.backup_dir()))

        from PyQt6.QtWidgets import QApplication  # imported late so DB tooling works without Qt

        from app.services.container import build_services
        from app.ui import appearance, fonts
        from app.ui.dialogs.first_run_dialog import FirstRunDialog
        from app.ui.dialogs.login_dialog import LoginDialog
        from app.ui.i18n.manager import I18n
        from app.ui.main_window import MainWindow

        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        fonts.load_fonts(paths.fonts_dir())

        services = build_services(conn)
        i18n = I18n(Catalog.load_dir(I18N_DIR), SettingsRepo(conn).get("language", DEFAULT_LANGUAGE))

        # Connected first, so it runs before any window re-translates itself.
        def on_language(code: str) -> None:
            appearance.apply(app, i18n)
            services.settings.set("language", code)

        i18n.language_changed.connect(on_language)
        appearance.apply(app, i18n)

        if services.auth.user_count() == 0:
            if FirstRunDialog(i18n, services).exec() != FirstRunDialog.DialogCode.Accepted:
                return 0

        while True:
            dialog = LoginDialog(i18n, services.auth)
            if dialog.exec() != LoginDialog.DialogCode.Accepted or dialog.user is None:
                return 0
            window = MainWindow(i18n, services, dialog.user)
            window.show()
            app.exec()
            if not window.signed_out:
                return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
