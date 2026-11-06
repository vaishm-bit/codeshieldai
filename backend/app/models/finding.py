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
