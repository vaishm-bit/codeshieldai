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
