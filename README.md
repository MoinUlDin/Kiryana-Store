# Kiryana POS

Offline point-of-sale for a kiryana shop. Python 3.12, PyQt6, SQLite, Windows 10+.

## Setup (Windows, VS Code terminal)
    py -3.12 -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements-dev.txt
    pytest
    python main.py

If PowerShell blocks activation, run once:
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

Copy your font files into assets/fonts (see the README.txt there).

For development, keep data inside the project instead of AppData:
    $env:KIRYANA_POS_DATA = "$PWD\dev_data"

## Ribbon shortcuts
Ctrl+F1 or double-click a tab: collapse / pin the ribbon.

## Users
The first launch asks you to create the Super Admin and the Owner. Cashiers are added from Settings > Users.
The terminal tool still works for the developer (for example to reset a forgotten Owner password):

    python -m tools.manage_users add --username ali --name "Ali Khan" --role cashier
    python -m tools.manage_users list
    python -m tools.manage_users reset-password --username ali
