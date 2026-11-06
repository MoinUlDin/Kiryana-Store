"""Read item sheets (.xlsx or .csv) into plain rows of text, and write the import template.
Rows keep their sheet position, so row numbers in error messages match what the user sees in Excel."""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

MAX_ROWS = 20000
MAX_BYTES = 20 * 1024 * 1024
SHEET_NAME = "Items"


class SpreadsheetError(Exception):
    """`code` is a translation key (import.error.*)."""

    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


def cell_to_text(value: object) -> str:
    """Excel hands back numbers as int/float. Turn them into text without float noise or exponents."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = format(Decimal(repr(value)), "f")
        return text[:-2] if text.endswith(".0") else text
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def read_rows(path: str | Path) -> list[list[str]]:
    path = Path(path)
    try:
        if path.stat().st_size > MAX_BYTES:
            raise SpreadsheetError("import.error.too_big", max=MAX_ROWS)
    except OSError as exc:
        raise SpreadsheetError("import.error.read") from exc
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv(path)
    if suffix in (".xlsx", ".xlsm"):
        return _read_xlsx(path)
    raise SpreadsheetError("import.error.read")   # includes old .xls: ask the user to save as .xlsx


def _read_csv(path: Path) -> list[list[str]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError) as exc:
        raise SpreadsheetError("import.error.read") from exc
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [[cell.strip() for cell in row] for row in csv.reader(text.splitlines(), dialect)]
    if len(rows) > MAX_ROWS + 1:
        raise SpreadsheetError("import.error.too_big", max=MAX_ROWS)
    return rows


def _read_xlsx(path: Path) -> list[list[str]]:
    from openpyxl import load_workbook  # imported here so the rest of the app works without it

    try:
        workbook = load_workbook(path, data_only=True)
    except Exception as exc:   # corrupt file, wrong format, password protected ...
        raise SpreadsheetError("import.error.read") from exc
    try:
        sheet = workbook[SHEET_NAME] if SHEET_NAME in workbook.sheetnames else workbook.worksheets[0]
        if sheet.max_row and sheet.max_row > MAX_ROWS + 1:
            raise SpreadsheetError("import.error.too_big", max=MAX_ROWS)
        rows: list[list[str]] = []
        for sheet_row in sheet.iter_rows():
            texts = [cell_to_text(cell.value) for cell in sheet_row]
            while texts and not texts[-1]:
                texts.pop()
            rows.append(texts)
        return rows
    finally:
        workbook.close()


TEMPLATE_HEADERS = ["short_code", "name_en", "name_ur", "category", "brand", "unit", "sale_price", "cost_price",
                    "barcode", "opening_stock", "low_stock_alert", "tax_percent", "allow_fraction"]
TEMPLATE_EXAMPLES = [
    ["SUG", "Sugar", "چینی", "Grocery", "", "kg", 150, 138, "", 50, 10, "", "yes"],
    ["LB-S", "Lifebuoy small", "لائف بوائے چھوٹا", "Soap", "Lifebuoy", "piece", 60, 52, "8901030865278", 100, 20, "", "no"],
]
TEMPLATE_HELP = [
    "HOW TO FILL THIS SHEET / اس شیٹ کو کیسے بھریں",
    "",
    "One row per item. Keep the header row (row 1) as it is. Delete the two example rows.",
    "ہر آئٹم کے لیے ایک قطار۔ پہلی قطار (عنوانات) نہ بدلیں۔ دو مثال والی قطاریں مٹا دیں۔",
    "",
    "Required: short_code, name_en (or name_ur), unit, sale_price.",
    "ضروری: short_code، name_en (یا name_ur)، unit، sale_price۔",
    "",
    "unit: piece, kg or litre (کلو، لیٹر، عدد also work). Prices are per unit, so per kg for kg items.",
    "یونٹ: piece، kg یا litre۔ قیمت فی یونٹ ہے، یعنی کلو والے آئٹم کی قیمت فی کلو۔",
    "",
    "opening_stock: how much is on the shelf now, in the item's unit (2.5 means 2.5 kg).",
    "opening_stock: ابھی شیلف پر کتنا ہے، آئٹم کے یونٹ میں (2.5 یعنی ڈھائی کلو)۔",
    "",
    "category and brand are created automatically if they do not exist yet.",
    "category اور brand موجود نہ ہوں تو خود بن جاتے ہیں۔",
    "",
    "allow_fraction: yes or no. Leave empty: yes for kg/litre, no for piece.",
    "Items whose short_code already exists are skipped (or updated if you choose that in the app).",
]


def write_template(path: str | Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAME
    sheet.append(TEMPLATE_HEADERS)
    for example in TEMPLATE_EXAMPLES:
        sheet.append(example)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2B6CB0")
    for index, header in enumerate(TEMPLATE_HEADERS, start=1):
        sheet.column_dimensions[sheet.cell(1, index).column_letter].width = max(14, len(header) + 4)
    for row in sheet.iter_rows(min_row=2, min_col=9, max_col=9):   # barcode column as text so digits are kept
        for cell in row:
            cell.number_format = "@"
    sheet.freeze_panes = "A2"
    help_sheet = workbook.create_sheet("Instructions")
    for line in TEMPLATE_HELP:
        help_sheet.append([line])
    help_sheet.column_dimensions["A"].width = 110
    help_sheet["A1"].font = Font(bold=True)
    workbook.save(path)
