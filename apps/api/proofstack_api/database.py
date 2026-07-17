"""Database engine and transactional session lifecycle."""

from collections.abc import Generator

from proofstack_shared.config import Settings, get_settings
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings) -> Engine:
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    database_engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    if settings.database_url.startswith("sqlite"):

        @event.listens_for(database_engine, "connect")
        def enable_sqlite_foreign_keys(connection: object, _: object) -> None:
            cursor = connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return database_engine


settings = get_settings()
engine = build_engine(settings)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
