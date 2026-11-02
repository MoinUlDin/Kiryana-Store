"""Developer tool: manage users straight from the command line.

    python -m tools.manage_users list
    python -m tools.manage_users add --username ali --name "Ali Khan" --role cashier
    python -m tools.manage_users reset-password --username ali

Passwords are typed at a hidden prompt, never on the command line.
Run from the project folder (set KIRYANA_POS_DATA first to target a dev database).
"""
from __future__ import annotations

import argparse
import getpass
import sys

from app import paths
from app.db.connection import connect
from app.db.migrator import migrate
from app.domain.user import ROLES, SYSTEM
from app.security.passwords import ValidationError
from app.services.container import build_services


def _ask_password() -> str:
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    add = sub.add_parser("add")
    add.add_argument("--username", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--role", choices=ROLES, required=True)
    reset = sub.add_parser("reset-password")
    reset.add_argument("--username", required=True)
    args = parser.parse_args(argv)

    paths.ensure_dirs()
    conn = connect(paths.db_path())
    try:
        migrate(conn, backup_dir=paths.backup_dir())
        services = build_services(conn)
        try:
            if args.command == "list":
                for row in conn.execute("SELECT username, display_name, role, is_active FROM users ORDER BY id"):
                    state = "active" if row["is_active"] else "disabled"
                    print(f"{row['username']:<20} {row['role']:<11} {state:<9} {row['display_name']}")
            elif args.command == "add":
                user = services.auth.create_user(SYSTEM, args.username, args.name, args.role, _ask_password())
                print(f"Created {user.role} '{user.username}'.")
            else:
                row = conn.execute("SELECT id FROM users WHERE username = ?", (args.username.strip(),)).fetchone()
                if row is None:
                    raise SystemExit("No such user.")
                services.auth.change_password(SYSTEM, row["id"], _ask_password())
                print("Password changed.")
        except ValidationError as exc:
            raise SystemExit(f"Invalid input: {exc.code} {exc.params}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
