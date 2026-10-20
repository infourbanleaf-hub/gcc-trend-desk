"""Google Sheets access through a service account, plus a small upsert helper."""
import json
import os

HEADER_FMT = {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
              "backgroundColor": {"red": 0.055, "green": 0.231, "blue": 0.263}}


def open_sheet(sheet_id):
    import gspread
    from google.oauth2.service_account import Credentials

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise RuntimeError("Missing GitHub secret GOOGLE_SERVICE_ACCOUNT_JSON.")
    creds = Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(sheet_id)


def tab(book, name, headers):
    """Return worksheet `name`, creating it with a styled header row if missing."""
    import gspread
    try:
        ws = book.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=name, rows=200, cols=len(headers))
        ws.update(range_name="A1", values=[headers])
        ws.format(f"A1:{_col(len(headers))}1", HEADER_FMT)
        ws.freeze(rows=1)
    return ws


def _col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def rewrite(ws, headers, rows):
    """Replace everything under the header with `rows` (list of lists)."""
    ws.batch_clear([f"A2:{_col(len(headers))}{max(ws.row_count, 2)}"])
    if rows:
        if ws.row_count < len(rows) + 1:
            ws.add_rows(len(rows) + 1 - ws.row_count)
        ws.update(range_name="A2", values=rows, value_input_option="RAW")


def append(ws, rows):
    if rows:
        ws.append_rows(rows, value_input_option="RAW")


def set_status(book, cell, text):
    """Write a one-line status into the Candidates tab (column Q), like the Apps Script jobs do."""
    try:
        book.worksheet("Candidates").update(range_name=cell, values=[[text]])
    except Exception:  # status is a convenience; never fail a run on it
        pass
