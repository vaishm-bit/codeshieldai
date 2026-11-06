"""Module 2 installer: database layer. Run once from the project root, then delete it."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NEW_FILES = {}
PATCHES = {}

# ---------------------------------------------------------------- new files
for pkg in (
    "backend/app/db/__init__.py",
    "backend/app/repositories/__init__.py",
):
    NEW_FILES[pkg] = ""

NEW_FILES["backend/app/db/base.py"] = r'''
"""Declarative base and small helpers shared by all models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Parent class of every ORM model."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())
'''

NEW_FILES["backend/app/db/types.py"] = r'''
"""Custom SQLAlchemy column types."""

from enum import Enum as PyEnum

from datetime import timezone

from sqlalchemy import DateTime, Enum
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """SQLite has no timezone support: store naive UTC, return aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


def enum_type(enum_cls: type[PyEnum], length: int = 32) -> Enum:
    """Store a Python enum by its value (e.g. 'Critical'), as a validated string."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
'''

NEW_FILES["backend/app/db/session.py"] = r'''
"""Engine, session factory, table creation and the FastAPI DB dependency."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BASE_DIR, get_settings
from app.db.base import Base


def configure_sqlite(engine: Engine) -> None:
    """SQLite ignores foreign keys unless this is switched on for every connection."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def build_database_url() -> str | URL:
    settings = get_settings()
    if settings.database_url:
        return settings.database_url
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return URL.create("sqlite", database=str(data_dir / "codeshield.db"))


def create_db_engine(url: str | URL | None = None) -> Engine:
    url = url or build_database_url()
    is_sqlite = make_url(url).get_backend_name() == "sqlite"
    kwargs = {"connect_args": {"check_same_thread": False}} if is_sqlite else {}
    engine = create_engine(url, **kwargs)
    if is_sqlite:
        configure_sqlite(engine)
    return engine


@lru_cache
def get_engine() -> Engine:
    return create_db_engine()


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def init_db(engine: Engine | None = None) -> None:
    """Create all tables if they do not exist yet."""
    from app import models  # noqa: F401  (importing registers the tables)

    Base.metadata.create_all(bind=engine or get_engine())


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
'''

NEW_FILES["backend/app/models/enums.py"] = r'''
"""Enumerations shared by models, schemas and services."""

import enum


class ScanStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(str, enum.Enum):
    PASTE = "paste"
    UPLOAD = "upload"


class Severity(str, enum.Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ScannerTool(str, enum.Enum):
    BANDIT = "bandit"
    SEMGREP = "semgrep"


class VulnCategory(str, enum.Enum):
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    HARDCODED_CREDENTIALS = "hardcoded_credentials"
    COMMAND_INJECTION = "command_injection"
    INSECURE_AUTHENTICATION = "insecure_authentication"
    INSECURE_CRYPTOGRAPHY = "insecure_cryptography"
    PATH_TRAVERSAL = "path_traversal"
    OTHER = "other"
'''

NEW_FILES["backend/app/models/scan.py"] = r'''
"""Scan: one submission of source code for analysis."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, new_id, utcnow
from app.db.types import UTCDateTime, enum_type
from app.models.enums import ScanStatus, SourceType

if TYPE_CHECKING:
    from app.models.finding import Finding
    from app.models.scanned_file import ScannedFile


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[ScanStatus] = mapped_column(
        enum_type(ScanStatus), default=ScanStatus.PENDING, index=True
    )
    source_type: Mapped[SourceType] = mapped_column(enum_type(SourceType))
    language: Mapped[str] = mapped_column(String(32))
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Which scanners ran, e.g. {"bandit": "ok", "semgrep": "unavailable: ..."}
    scanner_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    files: Mapped[list["ScannedFile"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", order_by="ScannedFile.id"
    )
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", order_by="Finding.id"
    )
'''

NEW_FILES["backend/app/models/scanned_file.py"] = r'''
"""ScannedFile: one source file (or pasted snippet) belonging to a scan."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.finding import Finding
    from app.models.scan import Scan


class ScannedFile(Base):
    __tablename__ = "scanned_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), index=True
    )
    # Display name only. Uploaded code is never written under this name on disk.
    filename: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    # Original source, kept so the UI can show original vs fixed code.
    content: Mapped[str] = mapped_column(Text)

    scan: Mapped["Scan"] = relationship(back_populates="files")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
'''

NEW_FILES["backend/app/models/finding.py"] = r'''
"""Finding: one vulnerability or bug reported by a scanner."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.db.types import UTCDateTime, enum_type
from app.models.enums import ScannerTool, Severity, VulnCategory

if TYPE_CHECKING:
    from app.models.scan import Scan
    from app.models.scanned_file import ScannedFile


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[int] = mapped_column(
        ForeignKey("scanned_files.id", ondelete="CASCADE"), index=True
    )

    tool: Mapped[ScannerTool] = mapped_column(enum_type(ScannerTool))
    rule_id: Mapped[str] = mapped_column(String(255))
    category: Mapped[VulnCategory] = mapped_column(enum_type(VulnCategory))
    severity: Mapped[Severity] = mapped_column(enum_type(Severity), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    cwe: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Filled by the AI layer (a later module); empty until then.
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    fixed_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    scan: Mapped["Scan"] = relationship(back_populates="findings")
    file: Mapped["ScannedFile"] = relationship(back_populates="findings")

    @property
    def filename(self) -> str:
        return self.file.filename
'''

NEW_FILES["backend/app/models/__init__.py"] = r'''
"""Importing this package registers every table on Base.metadata."""

from app.models.enums import ScannerTool, ScanStatus, Severity, SourceType, VulnCategory
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.scanned_file import ScannedFile

__all__ = [
    "Finding",
    "Scan",
    "ScannedFile",
    "ScannerTool",
    "ScanStatus",
    "Severity",
    "SourceType",
    "VulnCategory",
]
'''

NEW_FILES["backend/app/repositories/scan_repository.py"] = r'''
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
'''

NEW_FILES["backend/tests/conftest.py"] = r'''
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables)
from app.db.base import Base
from app.db.session import configure_sqlite


@pytest.fixture()
def db_session():
    """A fresh in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    configure_sqlite(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
'''

NEW_FILES["backend/tests/test_models.py"] = r'''
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
'''

NEW_FILES["backend/tests/test_repository.py"] = r'''
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
'''

NEW_FILES["backend/tests/test_session.py"] = r'''
from types import SimpleNamespace

from sqlalchemy import inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.db import session as session_module
from app.db.session import build_database_url, create_db_engine, get_db, init_db


def test_sqlite_engine_enables_foreign_keys():
    engine = create_db_engine("sqlite://")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
    engine.dispose()


def test_init_db_creates_tables(tmp_path):
    engine = create_db_engine(URL.create("sqlite", database=str(tmp_path / "t.db")))
    init_db(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"scans", "scanned_files", "findings"} <= tables
    engine.dispose()


def test_default_url_points_to_backend_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(session_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(session_module, "get_settings", lambda: SimpleNamespace(database_url=""))
    url = build_database_url()
    assert (tmp_path / "data").is_dir()
    assert url.database == str(tmp_path / "data" / "codeshield.db")


def test_configured_url_is_used(monkeypatch):
    monkeypatch.setattr(
        session_module, "get_settings", lambda: SimpleNamespace(database_url="sqlite://")
    )
    assert build_database_url() == "sqlite://"


def test_get_db_yields_and_closes_session(monkeypatch):
    engine = create_db_engine("sqlite://")
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)

    gen = get_db()
    db = next(gen)
    assert db.execute(text("select 1")).scalar() == 1
    gen.close()
    engine.dispose()
'''

# ---------------------------------------------------- edits to existing files
PATCHES["backend/requirements.txt"] = [
    (
        "pydantic-settings>=2.4,<3.0",
        "pydantic-settings>=2.4,<3.0\nsqlalchemy>=2.0,<3.0",
    ),
]

PATCHES["backend/app/core/config.py"] = [
    (
        "from functools import lru_cache\n",
        "from functools import lru_cache\nfrom pathlib import Path\n",
    ),
    (
        "class Settings(BaseSettings):",
        "# backend/ directory (this file lives at backend/app/core/config.py)\n"
        "BASE_DIR = Path(__file__).resolve().parents[2]\n\n\n"
        "class Settings(BaseSettings):",
    ),
    (
        '    log_level: str = "INFO"\n',
        '    log_level: str = "INFO"\n\n'
        "    # Leave empty to use the default SQLite file at backend/data/codeshield.db\n"
        '    database_url: str = ""\n',
    ),
]

PATCHES["backend/app/main.py"] = [
    (
        "from app.core.logging import setup_logging\n",
        "from app.core.logging import setup_logging\nfrom app.db.session import init_db\n",
    ),
    (
        '    yield\n    logger.info("Shutting down")',
        '    init_db()\n    logger.info("Database ready")\n    yield\n    logger.info("Shutting down")',
    ),
]

PATCHES["backend/.env.example"] = [
    (
        "LOG_LEVEL=INFO\n",
        "LOG_LEVEL=INFO\n\n# Leave empty to use backend/data/codeshield.db\nDATABASE_URL=\n",
    ),
]


def plan():
    writes, problems = {}, []

    for rel, content in NEW_FILES.items():
        path = ROOT / rel
        text = content.lstrip("\n")
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                problems.append(f"{rel} already exists with different content")
            continue
        writes[rel] = text

    for rel, patches in PATCHES.items():
        path = ROOT / rel
        if not path.exists():
            problems.append(f"{rel} not found")
            continue
        text = path.read_text(encoding="utf-8")
        changed = False
        for old, new in patches:
            if new in text:
                continue  # already applied
            if text.count(old) != 1:
                problems.append(f"{rel}: expected text not found exactly once: {old.strip()[:50]!r}")
                continue
            text = text.replace(old, new)
            changed = True
        if changed:
            writes[rel] = text

    return writes, problems


def main() -> None:
    if not (ROOT / "backend" / "app" / "main.py").exists():
        sys.exit("Run this from the project root (the folder that contains 'backend').")

    writes, problems = plan()
    if problems:
        print("Nothing was changed. Fix these first:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    for rel, text in writes.items():
        target = ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {rel}")

    print("\nDone." if writes else "\nAlready installed, nothing to do.")


if __name__ == "__main__":
    main()