"""
Kleine hulpmodule om de Claude Code sales-agent met de leadlijst in Google Sheets
te laten praten. Gebruikt een service account (zie SETUP.md voor de eenmalige
configuratie).

Installeren (eenmalig):
    pip install gspread google-auth

Gebruik (voorbeeld):
    from sheets_client import SheetsClient

    client = SheetsClient(
        credentials_path="credentials/service-account.json",
        sheet_id="1x6uZ9eusUVB8KOUxIiPhdcBu1cth3S_B5Oy9808hKTY",
    )

    leads = client.get_leads("Web & hostingpartijen")
    client.update_lead(
        "Web & hostingpartijen",
        bedrijfsnaam="Freshheads",
        updates={"Status": "Gesprek gepland", "Laatste contact": "17-09-2026"},
    )
    client.append_lead("Onderwijs", {
        "Prioriteit": "Hoog",
        "Bedrijfsnaam": "Voorbeeld Basisschool",
        ...
    })
    capaciteit = client.get_capaciteit()
"""

from __future__ import annotations

import datetime
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# De koptekst-rij (kolomnamen) staat op rij 3 in elk doelgroep-tabblad;
# data begint op rij 4. Zie de bestaande leadlijst-structuur.
HEADER_ROW = 3
DATA_START_ROW = 4

CAPACITEIT_HEADERS = [
    "Weekstart",
    "Actieve opdrachten",
    "Toegezegde uren/week",
    "Toegezegde omzet/week",
    "Status",
]


class SheetsClient:
    def __init__(self, credentials_path: str, sheet_id: str):
        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        self._gc = gspread.authorize(creds)
        self._sheet = self._gc.open_by_key(sheet_id)

    # ---------- Doelgroep-tabbladen (leads) ----------

    def get_leads(self, tab_name: str) -> list[dict[str, Any]]:
        """Geeft alle leads terug als lijst van dicts (kolomnaam -> waarde)."""
        ws = self._sheet.worksheet(tab_name)
        headers = ws.row_values(HEADER_ROW)
        rows = ws.get_all_values()[DATA_START_ROW - 1 :]
        leads = []
        for i, row in enumerate(rows):
            if not row or not row[1]:  # kolom B = Bedrijfsnaam leeg -> geen lead
                continue
            record = dict(zip(headers, row))
            record["_row_number"] = DATA_START_ROW + i  # voor updates
            leads.append(record)
        return leads

    def update_lead(self, tab_name: str, bedrijfsnaam: str, updates: dict[str, Any]) -> bool:
        """Werkt kolommen bij voor de rij met de opgegeven bedrijfsnaam."""
        ws = self._sheet.worksheet(tab_name)
        headers = ws.row_values(HEADER_ROW)
        leads = self.get_leads(tab_name)
        target = next(
            # Onderwijs-tabblad gebruikt "Schoolnaam" i.p.v. "Bedrijfsnaam"
            (
                l
                for l in leads
                if (l.get("Bedrijfsnaam") or l.get("Schoolnaam") or "").strip().lower() == bedrijfsnaam.strip().lower()
            ),
            None,
        )
        if not target:
            return False
        row_num = target["_row_number"]
        for col_name, value in updates.items():
            if col_name not in headers:
                continue
            col_num = headers.index(col_name) + 1
            ws.update_cell(row_num, col_num, value)
        return True

    def append_lead(self, tab_name: str, lead: dict[str, Any]) -> None:
        """Voegt een nieuwe lead-rij toe onderaan het tabblad."""
        ws = self._sheet.worksheet(tab_name)
        headers = ws.row_values(HEADER_ROW)
        row = [lead.get(h, "") for h in headers]
        ws.append_row(row, table_range=f"A{DATA_START_ROW}")

    def create_tab_if_missing(self, tab_name: str, headers: list[str], title_row: str, instruction_row: str) -> None:
        """Maakt een nieuw doelgroep-tabblad aan met dezelfde structuur als de rest."""
        existing = [ws.title for ws in self._sheet.worksheets()]
        if tab_name in existing:
            return
        ws = self._sheet.add_worksheet(title=tab_name, rows=400, cols=len(headers))
        ws.update("A1", [[title_row]])
        ws.update("A2", [[instruction_row]])
        ws.update(f"A{HEADER_ROW}", [headers])

    def ensure_column(self, tab_name: str, column_name: str) -> None:
        """Voegt een kolom toe aan het eind van de koptekst-rij als die nog niet bestaat."""
        ws = self._sheet.worksheet(tab_name)
        headers = ws.row_values(HEADER_ROW)
        if column_name in headers:
            return
        col_num = len(headers) + 1
        if ws.col_count < col_num:
            ws.add_cols(col_num - ws.col_count)
        ws.update_cell(HEADER_ROW, col_num, column_name)

    def set_dropdown(self, tab_name: str, column_name: str, options: list[str]) -> None:
        """Zet een keuzemenu op een kolom (vanaf de eerste datarij)."""
        ws = self._sheet.worksheet(tab_name)
        col_index = ws.row_values(HEADER_ROW).index(column_name)
        self._sheet.batch_update({"requests": [{
            "setDataValidation": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": DATA_START_ROW - 1,
                    "startColumnIndex": col_index,
                    "endColumnIndex": col_index + 1,
                },
                "rule": {
                    "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": o} for o in options]},
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        }]})

    # ---------- Capaciteit-tabblad ----------

    def get_capaciteit(self) -> dict[str, Any] | None:
        """Geeft de meest recente capaciteitsregel terug, of None als leeg."""
        existing = [ws.title for ws in self._sheet.worksheets()]
        if "Capaciteit" not in existing:
            return None
        ws = self._sheet.worksheet("Capaciteit")
        rows = ws.get_all_records()
        if not rows:
            return None
        return rows[-1]

    def log_capaciteit(
        self,
        actieve_opdrachten: str,
        uren_per_week: float,
        omzet_per_week: float,
        weekstart: str | None = None,
    ) -> None:
        existing = [ws.title for ws in self._sheet.worksheets()]
        if "Capaciteit" not in existing:
            ws = self._sheet.add_worksheet(title="Capaciteit", rows=200, cols=5)
            ws.update("A1", [CAPACITEIT_HEADERS])
        else:
            ws = self._sheet.worksheet("Capaciteit")

        status = "Acquireren UIT" if (uren_per_week >= 24 or omzet_per_week >= 1800) else "Acquireren AAN"
        weekstart = weekstart or datetime.date.today().isoformat()
        ws.append_row([weekstart, actieve_opdrachten, uren_per_week, omzet_per_week, status])
