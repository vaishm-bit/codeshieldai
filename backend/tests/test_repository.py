from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ValidationFailedError
from app.models.enums import ScannerTool, ScanStatus, Severity, SourceType, VulnCategory
from app.repositories import scan_repository as repo
from app.repositories.scan_repository import FileData, NewFinding


def new_scan(db, name="app.py", content="import os\n"):
    return repo.create_scan(
        db,
        source_type=SourceType.PASTE,
        language="python",
        files=[FileData(filename=name, content=content)],
    )


def new_finding(**overrides):
    data = dict(
        filename="app.py",
        tool=ScannerTool.BANDIT,
        rule_id="B602",
        category=VulnCategory.COMMAND_INJECTION,
        severity=Severity.HIGH,
        title="Test finding",
        description="Test description",
        line_start=3,
    )
    data.update(overrides)
    return NewFinding(**data)


def test_create_scan_stores_file_metadata(db_session):
    scan = new_scan(db_session, content="print('hi')\n")
    stored = scan.files[0]
    assert scan.file_count == 1
    assert stored.size_bytes == len("print('hi')\n".encode())
    assert len(stored.sha256) == 64
    assert stored.content == "print('hi')\n"
    assert stored.language == "python"


def test_get_scan_unknown_returns_none(db_session):
    assert repo.get_scan(db_session, "missing") is None


def test_add_findings_and_get_scan(db_session):
    scan = new_scan(db_session)
    created = repo.add_findings(db_session, scan, [new_finding(), new_finding(line_start=9)])
    assert len(created) == 2

    loaded = repo.get_scan(db_session, scan.id)
    assert len(loaded.findings) == 2
    assert loaded.findings[0].filename == "app.py"


def test_add_findings_rejects_unknown_file(db_session):
    scan = new_scan(db_session)
    with pytest.raises(ValidationFailedError):
        repo.add_findings(db_session, scan, [new_finding(filename="other.py")])


def test_list_scans_newest_first_with_pagination(db_session):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = []
    for i in range(3):
        scan = new_scan(db_session)
        scan.created_at = base + timedelta(minutes=i)
        db_session.commit()
        ids.append(scan.id)

    assert [s.id for s in repo.list_scans(db_session)] == list(reversed(ids))
    assert [s.id for s in repo.list_scans(db_session, limit=1, offset=1)] == [ids[1]]
    assert repo.count_scans(db_session) == 3


def test_severity_counts_include_zeros(db_session):
    scan = new_scan(db_session)
    repo.add_findings(
        db_session,
        scan,
        [new_finding(severity=Severity.HIGH), new_finding(severity=Severity.HIGH)],
    )
    counts = repo.severity_counts(db_session, scan.id)
    assert counts[Severity.HIGH] == 2
    assert counts[Severity.CRITICAL] == 0
    assert set(counts) == set(Severity)


def test_status_transitions(db_session):
    scan = new_scan(db_session)
    repo.mark_running(db_session, scan)
    assert scan.status == ScanStatus.RUNNING

    repo.mark_completed(
        db_session, scan, risk_score=42.5, scanner_status={"bandit": "ok"}
    )
    assert scan.status == ScanStatus.COMPLETED
    assert scan.risk_score == 42.5
    assert scan.completed_at is not None
    assert scan.scanner_status == {"bandit": "ok"}


def test_mark_failed_records_message(db_session):
    scan = new_scan(db_session)
    repo.mark_failed(db_session, scan, "boom")
    assert scan.status == ScanStatus.FAILED
    assert scan.error_message == "boom"


def test_delete_scan(db_session):
    scan = new_scan(db_session)
    assert repo.delete_scan(db_session, scan.id) is True
    assert repo.get_scan(db_session, scan.id) is None
    assert repo.delete_scan(db_session, scan.id) is False
