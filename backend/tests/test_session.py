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
