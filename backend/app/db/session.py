"""Engine and session helpers for the PostgreSQL-backed persistence layer."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional, Protocol

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings, get_settings


class SessionManager(Protocol):
    """Protocol describing objects that can provide SQLAlchemy sessions."""

    def __call__(self) -> Session:  # pragma: no cover - protocol definition
        ...


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def _build_engine(settings: Settings) -> Engine:
    database_url = settings.database_url
    if not database_url:
        raise RuntimeError("ARCADIA_DATABASE_URL must be configured before using the database.")

    kwargs: dict[str, object] = {
        "echo": settings.database_echo,
        "future": True,
        "pool_pre_ping": True,
    }

    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow

    return create_engine(database_url, **kwargs)


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = _build_engine(settings)
        _session_factory = sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope(*, commit: bool = True) -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        if commit:
            session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        raise
    finally:
        session.close()


def get_session_dependency() -> Generator[Session, None, None]:
    with session_scope() as session:
        yield session


def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


__all__ = [
    "SessionManager",
    "dispose_engine",
    "get_engine",
    "get_session_factory",
    "get_session_dependency",
    "session_scope",
]
