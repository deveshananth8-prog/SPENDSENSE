"""SQLAlchemy engine, session factory, and database initialization."""

from collections.abc import Generator
import logging
import os
from pathlib import Path
import tempfile

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://"):]
    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        return "postgresql+psycopg://" + database_url[len("postgresql://"):]
    return database_url


def _resolve_writable_sqlite_url(url: str) -> str:
    if not url.startswith("sqlite:///") or url.endswith(":memory:"):
        return url
    db_file = Path(url[len("sqlite:///"):])
    target_dir = db_file.parent if str(db_file.parent) not in {"", "."} else Path(".")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        can_write = os.access(target_dir, os.W_OK | os.X_OK) and (
            not db_file.exists() or os.access(db_file, os.W_OK)
        )
        if can_write:
            return url
    except OSError:
        pass
    fallback = Path(tempfile.gettempdir()) / "spendsense.db"
    logger.warning(
        "SQLite path %s is not writable; falling back to temporary database %s.",
        db_file,
        fallback,
    )
    return f"sqlite:///{fallback}"


def _make_engine(database_url: str):
    url = _resolve_writable_sqlite_url(_normalize_database_url(database_url))
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    eng = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _enable_sqlite_fk(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return eng


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
