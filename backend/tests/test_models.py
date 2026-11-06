from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, StatementError

from app.models import Finding, Scan, ScannedFile
from app.models.enums import ScannerTool, ScanStatus, Severity, SourceType, VulnCategory


def make_scan(db):
    scan = Scan(source_type=SourceType.PASTE, language="python", file_count=1)
    scan.files.append(
        ScannedFile(
            filename="app.py",
            language="python",
            size_bytes=10,
            sha256="0" * 64,
            content="print('x')",
        )
    )
    db.add(scan)
    db.commit()
    return scan


def make_finding(scan, **overrides):
    data = dict(
        scan_id=scan.id,
        file_id=scan.files[0].id,
        tool=ScannerTool.BANDIT,
        rule_id="B602",
        category=VulnCategory.COMMAND_INJECTION,
        severity=Severity.HIGH,
        title="Test finding",
        description="Test description",
        line_start=3,
    )
    data.update(overrides)
    return Finding(**data)


def count(db, model):
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def test_scan_defaults(db_session):
    scan = make_scan(db_session)
    assert len(scan.id) == 36
    assert scan.status == ScanStatus.PENDING
    assert scan.risk_score is None
    assert scan.created_at.tzinfo is not None
    assert scan.created_at.utcoffset() == timedelta(0)


def test_relationships(db_session):
    scan = make_scan(db_session)
    db_session.add(make_finding(scan))
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.get(Scan, scan.id)
    assert len(loaded.files) == 1
    assert len(loaded.findings) == 1
    assert loaded.findings[0].filename == "app.py"
    assert loaded.findings[0].scan.id == scan.id


def test_enum_roundtrip_and_filter(db_session):
    scan = make_scan(db_session)
    db_session.add(make_finding(scan, severity=Severity.CRITICAL))
    db_session.add(make_finding(scan, severity=Severity.LOW))
    db_session.commit()
    db_session.expire_all()

    rows = db_session.execute(
        select(Finding).where(Finding.severity == Severity.CRITICAL)
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].severity is Severity.CRITICAL


def test_json_scanner_status_roundtrip(db_session):
    scan = make_scan(db_session)
    scan.scanner_status = {"bandit": "ok", "semgrep": "unavailable"}
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(Scan, scan.id).scanner_status == {
        "bandit": "ok",
        "semgrep": "unavailable",
    }


def test_cascade_delete_removes_children(db_session):
    scan = make_scan(db_session)
    db_session.add(make_finding(scan))
    db_session.commit()

    db_session.delete(scan)
    db_session.commit()

    assert count(db_session, Scan) == 0
    assert count(db_session, ScannedFile) == 0
    assert count(db_session, Finding) == 0


def test_foreign_keys_are_enforced(db_session):
    db_session.add(
        Finding(
            scan_id="does-not-exist",
            file_id=999,
            tool=ScannerTool.BANDIT,
            rule_id="B101",
            category=VulnCategory.OTHER,
            severity=Severity.LOW,
            title="x",
            description="x",
            line_start=1,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_invalid_enum_value_is_rejected(db_session):
    db_session.add(Scan(source_type="bogus", language="python"))
    with pytest.raises((StatementError, LookupError)):
        db_session.commit()
    db_session.rollback()
