import json
import re
from pathlib import Path

import pytest

from incidentform.__main__ import main
from incidentform.pdf import Pdf, text_width, wrap
from incidentform.report import TEMPLATE, load_record, render, validate

BS = chr(92)
EX = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def record():
    return load_record(str(EX / "incident_slip.json"))


def test_sample_record_is_valid(record):
    assert validate(record) == []


def test_template_is_valid_except_placeholder_date():
    problems = validate(dict(TEMPLATE))
    assert problems == []


def test_missing_required_field(record):
    del record["location"]
    assert "location: required" in validate(record)


def test_blank_string_counts_as_missing(record):
    record["reported_by"] = "   "
    assert "reported_by: required" in validate(record)


def test_bad_date_and_time(record):
    record["date"], record["time"] = "12/11/2026", "9am"
    problems = validate(record)
    assert "date: use YYYY-MM-DD" in problems and "time: use 24 hour HH:MM" in problems


def test_future_date_rejected(record):
    record["date"] = "2999-01-01"
    assert "date: is in the future" in validate(record)


def test_unknown_type_and_severity(record):
    record["incident_type"], record["severity"] = "Spill", "Huge"
    problems = validate(record)
    assert any(p.startswith("incident_type") for p in problems)
    assert any(p.startswith("severity") for p in problems)


def test_high_severity_needs_actions(record):
    record["severity"] = "High"
    record["corrective_actions"] = []
    assert any("required for High" in p for p in validate(record))


def test_action_due_before_incident(record):
    record["corrective_actions"][0]["due"] = "2026-01-01"
    assert any("before the incident date" in p for p in validate(record))


def test_action_needs_owner(record):
    record["corrective_actions"][1]["owner"] = ""
    assert "corrective_actions[2]: owner required" in validate(record)


def test_wrap_respects_width():
    for line in wrap("word " * 80, 10, 200):
        assert text_width(line, 10) <= 200


def test_wrap_splits_long_word_and_keeps_newlines():
    assert len(wrap("x" * 200, 10, 100)) > 1
    assert wrap("a\nb", 10, 100) == ["a", "b"]


def test_pdf_structure_and_xref(record):
    data = render(record)
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    start = int(re.search(rb"startxref\n(\d+)", data).group(1))
    assert data[start:start + 4] == b"xref"
    table = data[start:].split(b"\n")[3:]
    for number, row in enumerate(table[:6], start=1):
        offset = int(row[:10])
        assert data[offset:].startswith(f"{number} 0 obj".encode())


def test_pdf_contains_text(record):
    data = render(record)
    assert b"INCIDENT REPORT" in data and b"INC-2026-0042" in data and b"Sam Ortiz" in data


def test_long_report_adds_pages(record):
    record["description"] = "Long text. " * 900
    data = render(record)
    assert b"Page 1 of " in data and b"/Count 1 " not in data


def test_special_characters_are_escaped():
    pdf = Pdf("t")
    pdf.text(10, 10, "a (b) " + BS + " c")
    assert ("a " + BS + "(b" + BS + ") " + BS + BS + " c").encode() in pdf.to_bytes()


def test_cli_flow(tmp_path, capsys):
    out = tmp_path / "r.pdf"
    assert main(["validate", str(EX / "incident_slip.json")]) == 0
    assert main(["validate", str(EX / "incident_incomplete.json")]) == 1
    assert main(["render", str(EX / "incident_incomplete.json"), "--out", str(out)]) == 1
    assert not out.exists()
    assert main(["render", str(EX / "incident_incomplete.json"), "--out", str(out), "--force"]) == 0
    assert out.read_bytes().startswith(b"%PDF")
    assert main(["validate", str(tmp_path / "none.json")]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    assert main(["validate", str(bad)]) == 2
    assert main(["template"]) == 0
