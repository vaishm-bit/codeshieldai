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
