"""Validate an incident record and lay it out as a PDF form."""

from __future__ import annotations

import json
from datetime import date, datetime

from .pdf import PAGE_H, PAGE_W, Pdf, text_width, wrap

INCIDENT_TYPES = ["Injury", "Near miss", "Property damage", "Security", "Environmental", "Equipment failure", "Other"]
SEVERITIES = ["Low", "Medium", "High", "Critical"]
REQUIRED = ["incident_id", "date", "time", "location", "reported_by", "incident_type", "severity", "description"]
TEMPLATE = {
    "incident_id": "INC-2026-0001",
    "date": "2026-11-18",
    "time": "14:30",
    "location": "Building A, Level 2, east corridor",
    "reported_by": "Name and role",
    "incident_type": "Near miss",
    "severity": "Low",
    "description": "What happened, in order, in plain words.",
    "people_involved": [{"name": "Name", "role": "Role", "injury": "None"}],
    "witnesses": ["Name"],
    "immediate_action": "What was done at the time.",
    "root_cause": "Why it happened.",
    "corrective_actions": [{"action": "What will change", "owner": "Name", "due": "2026-12-15"}],
    "follow_up_required": True,
}

INK = (0.1, 0.12, 0.15)
MUTED = (0.42, 0.45, 0.5)
ACCENT = (0.12, 0.27, 0.45)
SEV_COLOR = {"Low": (0.25, 0.55, 0.3), "Medium": (0.85, 0.65, 0.1), "High": (0.85, 0.4, 0.1), "Critical": (0.75, 0.12, 0.12)}


def load_record(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("the incident file must contain one JSON object")
    return data


def validate(record: dict) -> list[str]:
    """Return a list of problems; empty means the record is complete and consistent."""
    problems: list[str] = []
    for key in REQUIRED:
        value = record.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append(f"{key}: required")
    when = None
    if record.get("date"):
        try:
            when = datetime.strptime(str(record["date"]), "%Y-%m-%d").date()
            if when > date.today():
                problems.append("date: is in the future")
        except ValueError:
            problems.append("date: use YYYY-MM-DD")
    if record.get("time"):
        try:
            datetime.strptime(str(record["time"]), "%H:%M")
        except ValueError:
            problems.append("time: use 24 hour HH:MM")
    if record.get("incident_type") and record["incident_type"] not in INCIDENT_TYPES:
        problems.append(f"incident_type: must be one of {', '.join(INCIDENT_TYPES)}")
    if record.get("severity") and record["severity"] not in SEVERITIES:
        problems.append(f"severity: must be one of {', '.join(SEVERITIES)}")
    for i, person in enumerate(record.get("people_involved") or [], start=1):
        if not isinstance(person, dict) or not person.get("name"):
            problems.append(f"people_involved[{i}]: name required")
    for i, item in enumerate(record.get("corrective_actions") or [], start=1):
        if not isinstance(item, dict) or not item.get("action"):
            problems.append(f"corrective_actions[{i}]: action required")
            continue
        if not item.get("owner"):
            problems.append(f"corrective_actions[{i}]: owner required")
        if item.get("due"):
            try:
                due = datetime.strptime(str(item["due"]), "%Y-%m-%d").date()
                if when and due < when:
                    problems.append(f"corrective_actions[{i}]: due date is before the incident date")
            except ValueError:
                problems.append(f"corrective_actions[{i}]: due must be YYYY-MM-DD")
    if record.get("severity") in ("High", "Critical") and not record.get("corrective_actions"):
        problems.append("corrective_actions: required for High and Critical incidents")
    return problems


class _Layout:
    LEFT, RIGHT, TOP, BOTTOM = 54.0, PAGE_W - 54.0, PAGE_H - 54.0, 60.0

    def __init__(self, pdf: Pdf):
        self.pdf = pdf
        self.y = self.TOP

    def need(self, height: float) -> None:
        if self.y - height < self.BOTTOM:
            self.pdf.new_page()
            self.y = self.TOP

    def heading(self, title: str) -> None:
        self.need(40)
        self.y -= 10
        self.pdf.text(self.LEFT, self.y, title.upper(), 10, True, ACCENT)
        self.y -= 5
        self.pdf.hline(self.LEFT, self.RIGHT, self.y, ACCENT, 1.0)
        self.y -= 14

    def paragraph(self, text: str, size: float = 10) -> None:
        for line in wrap(text or "-", size, self.RIGHT - self.LEFT):
            self.need(size + 4)
            self.pdf.text(self.LEFT, self.y, line, size, False, INK)
            self.y -= size + 3.5

    def fields(self, pairs: list[tuple[str, str]], columns: int = 2) -> None:
        width = (self.RIGHT - self.LEFT) / columns
        for start in range(0, len(pairs), columns):
            row = pairs[start:start + columns]
            lines = [wrap(value or "-", 10, width - 12) for _, value in row]
            height = 12 + 13 * max(len(x) for x in lines)
            self.need(height)
            for n, ((label, _), value_lines) in enumerate(zip(row, lines)):
                x = self.LEFT + n * width
                self.pdf.text(x, self.y, label.upper(), 7, True, MUTED)
                for k, line in enumerate(value_lines):
                    self.pdf.text(x, self.y - 12 - 13 * k, line, 10, False, INK)
            self.y -= height + 4

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        total = self.RIGHT - self.LEFT
        cols = [w * total for w in widths]
        self.need(40)
        self.pdf.rect(self.LEFT, self.y - 15, total, 18, fill=(0.93, 0.95, 0.97))
        x = self.LEFT
        for head, w in zip(headers, cols):
            self.pdf.text(x + 5, self.y - 9, head.upper(), 7.5, True, MUTED)
            x += w
        self.y -= 18
        for row in rows:
            cells = [wrap(c or "-", 9.5, w - 10) for c, w in zip(row, cols)]
            height = 6 + 12 * max(len(c) for c in cells)
            self.need(height + 2)
            x = self.LEFT
            for lines, w in zip(cells, cols):
                for k, line in enumerate(lines):
                    self.pdf.text(x + 5, self.y - 10 - 12 * k, line, 9.5, False, INK)
                x += w
            self.y -= height
            self.pdf.hline(self.LEFT, self.RIGHT, self.y + 1)
        self.y -= 6


def render(record: dict) -> bytes:
    """Draw the incident record as a PDF and return its bytes."""
    pdf = Pdf(f"Incident report {record.get('incident_id', '')}".strip())
    lay = _Layout(pdf)
    pdf.rect(0, PAGE_H - 92, PAGE_W, 92, fill=ACCENT)
    pdf.text(lay.LEFT, PAGE_H - 52, "INCIDENT REPORT", 22, True, (1, 1, 1))
    pdf.text(lay.LEFT, PAGE_H - 74, str(record.get("incident_id", "")), 11, False, (0.85, 0.9, 0.95))
    severity = str(record.get("severity", ""))
    chip = text_width(severity.upper(), 10, True) + 22
    pdf.rect(lay.RIGHT - chip, PAGE_H - 62, chip, 24, fill=SEV_COLOR.get(severity, MUTED))
    pdf.text(lay.RIGHT - chip + 11, PAGE_H - 54, severity.upper(), 10, True, (1, 1, 1))
    lay.y = PAGE_H - 92 - 18

    lay.heading("Incident details")
    lay.fields([("Date", str(record.get("date", ""))), ("Time", str(record.get("time", ""))),
                ("Location", str(record.get("location", ""))), ("Type", str(record.get("incident_type", ""))),
                ("Reported by", str(record.get("reported_by", ""))),
                ("Follow up required", "Yes" if record.get("follow_up_required") else "No")])
    lay.heading("What happened")
    lay.paragraph(str(record.get("description", "")))
    people = record.get("people_involved") or []
    lay.heading("People involved")
    if people:
        lay.table(["Name", "Role", "Injury or effect"],
                  [[p.get("name", ""), p.get("role", ""), p.get("injury", "")] for p in people], [0.38, 0.30, 0.32])
    else:
        lay.paragraph("None recorded.")
    witnesses = record.get("witnesses") or []
    lay.heading("Witnesses")
    lay.paragraph(", ".join(witnesses) if witnesses else "None recorded.")
    lay.heading("Immediate action taken")
    lay.paragraph(str(record.get("immediate_action", "")))
    lay.heading("Root cause")
    lay.paragraph(str(record.get("root_cause", "")))
    actions = record.get("corrective_actions") or []
    lay.heading("Corrective actions")
    if actions:
        lay.table(["Action", "Owner", "Due"],
                  [[a.get("action", ""), a.get("owner", ""), a.get("due", "")] for a in actions], [0.58, 0.24, 0.18])
    else:
        lay.paragraph("None recorded.")
    lay.heading("Sign off")
    lay.need(60)
    for n, label in enumerate(["Reported by", "Reviewed by"]):
        x = lay.LEFT + n * 270
        pdf.hline(x, x + 230, lay.y - 24, (0.2, 0.2, 0.2), 0.8)
        pdf.text(x, lay.y - 36, f"{label}: signature and date", 8, False, MUTED)
    total = len(pdf.pages)
    for number, ops in enumerate(pdf.pages, start=1):
        pdf.pages, saved = [ops], pdf.pages
        pdf.text(lay.LEFT, 34, f"{record.get('incident_id', '')}", 8, False, MUTED)
        footer = f"Page {number} of {total}"
        pdf.text(lay.RIGHT - text_width(footer, 8), 34, footer, 8, False, MUTED)
        pdf.pages = saved
    return pdf.to_bytes()
