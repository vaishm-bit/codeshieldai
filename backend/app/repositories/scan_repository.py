"""Database access for scans and findings. No HTTP or scanner logic lives here."""

import hashlib
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ValidationFailedError
from app.db.base import utcnow
from app.models import (
    Finding,
    Scan,
    ScannedFile,
    ScannerTool,
    ScanStatus,
    Severity,
    SourceType,
    VulnCategory,
)


@dataclass(frozen=True)
class FileData:
    filename: str
    content: str
    language: str | None = None


@dataclass(frozen=True)
class NewFinding:
    filename: str
    tool: ScannerTool
    rule_id: str
    category: VulnCategory
    severity: Severity
    title: str
    description: str
    line_start: int
    line_end: int | None = None
    code_snippet: str | None = None
    cwe: str | None = None
    confidence: str | None = None


def create_scan(
    db: Session, *, source_type: SourceType, language: str, files: list[FileData]
) -> Scan:
    scan = Scan(source_type=source_type, language=language, file_count=len(files))
    for item in files:
        raw = item.content.encode("utf-8")
        scan.files.append(
            ScannedFile(
                filename=item.filename,
                language=item.language or language,
                size_bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                content=item.content,
            )
        )
    db.add(scan)
    db.commit()
    return scan


def get_scan(db: Session, scan_id: str) -> Scan | None:
    stmt = (
        select(Scan)
        .where(Scan.id == scan_id)
        .options(
            selectinload(Scan.files),
            selectinload(Scan.findings).selectinload(Finding.file),
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_scans(db: Session, *, limit: int = 20, offset: int = 0) -> list[Scan]:
    stmt = (
        select(Scan)
        .order_by(Scan.created_at.desc(), Scan.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars())


def count_scans(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Scan)).scalar_one()


def add_findings(db: Session, scan: Scan, findings: list[NewFinding]) -> list[Finding]:
    """Attach findings to a scan. Filenames must be unique within a scan."""
    files = {f.filename: f for f in scan.files}
    rows: list[Finding] = []
    for item in findings:
        file = files.get(item.filename)
        if file is None:
            raise ValidationFailedError(f"Finding refers to unknown file: {item.filename}")
        rows.append(
            Finding(
                scan_id=scan.id,
                file_id=file.id,
                tool=item.tool,
                rule_id=item.rule_id,
                category=item.category,
                severity=item.severity,
                title=item.title,
                description=item.description,
                line_start=item.line_start,
                line_end=item.line_end,
                code_snippet=item.code_snippet,
                cwe=item.cwe,
                confidence=item.confidence,
            )
        )
    db.add_all(rows)
    db.commit()
    db.expire(scan, ["findings"])
    return rows


def severity_counts(db: Session, scan_id: str) -> dict[Severity, int]:
    rows = db.execute(
        select(Finding.severity, func.count(Finding.id))
        .where(Finding.scan_id == scan_id)
        .group_by(Finding.severity)
    ).all()
    counts = {severity: 0 for severity in Severity}
    for severity, count in rows:
        counts[severity] = count
    return counts


def mark_running(db: Session, scan: Scan) -> Scan:
    scan.status = ScanStatus.RUNNING
    db.commit()
    return scan


def mark_completed(
    db: Session, scan: Scan, *, risk_score: float, scanner_status: dict
) -> Scan:
    scan.status = ScanStatus.COMPLETED
    scan.risk_score = risk_score
    scan.scanner_status = scanner_status
    scan.completed_at = utcnow()
    db.commit()
    return scan


def mark_failed(db: Session, scan: Scan, message: str) -> Scan:
    scan.status = ScanStatus.FAILED
    scan.error_message = message[:2000]
    scan.completed_at = utcnow()
    db.commit()
    return scan


def delete_scan(db: Session, scan_id: str) -> bool:
    scan = db.get(Scan, scan_id)
    if scan is None:
        return False
    db.delete(scan)
    db.commit()
    return True
