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
