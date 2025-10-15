"""Utility for running Alembic migrations with retry-aware database checks.

This script is invoked during deploys to ensure database schema drift is resolved
before the application starts accepting traffic (Phase 21).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

LOGGER = logging.getLogger("arcadia.migrations")
DEFAULT_TIMEOUT = int(os.getenv("ARCADIA_DB_MIGRATION_TIMEOUT", "60"))
DEFAULT_POLL_INTERVAL = float(os.getenv("ARCADIA_DB_MIGRATION_POLL_INTERVAL", "3"))
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Alembic migrations with readiness checks.")
    parser.add_argument(
        "--revision",
        default=os.getenv("ARCADIA_DB_MIGRATION_REVISION", "head"),
        help="Revision identifier to upgrade to (default: head).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Seconds to wait for the database to become available (default: {DEFAULT_TIMEOUT}).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help=f"Seconds between readiness probes (default: {DEFAULT_POLL_INTERVAL}).",
    )
    parser.add_argument(
        "--config",
        default=str(BACKEND_ROOT / "alembic.ini"),
        help="Path to alembic.ini configuration file.",
    )
    return parser.parse_args(argv)


def get_alembic_config(config_path: str) -> Config:
    config = Config(config_path)
    script_location = BACKEND_ROOT / "alembic"
    config.set_main_option("script_location", str(script_location))
    return config


def resolve_database_url(config: Config) -> str:
    url = config.get_main_option("sqlalchemy.url")
    if not url or url == "%(ARCADIA_DATABASE_URL)s":
        env_url = os.getenv("ARCADIA_DATABASE_URL")
        if env_url:
            config.set_main_option("sqlalchemy.url", env_url)
            return env_url
        raise RuntimeError("ARCADIA_DATABASE_URL must be set before running migrations.")
    return url


def wait_for_database(database_url: str, *, timeout: int, poll_interval: float) -> None:
    """Poll the database until a basic SELECT succeeds or timeout is reached."""
    deadline = time.time() + timeout
    engine: Optional[Engine] = None
    last_error: Optional[Exception] = None

    try:
        engine = create_engine(database_url, future=True, pool_pre_ping=True)
        while time.time() < deadline:
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                LOGGER.info("Database is reachable.")
                return
            except OperationalError as exc:  # transient connectivity
                last_error = exc
                LOGGER.warning("Database not ready yet: %s", exc)
            except SQLAlchemyError as exc:
                last_error = exc
                LOGGER.error("Database error during readiness probe: %s", exc)
                break
            time.sleep(poll_interval)
    finally:
        if engine is not None:
            engine.dispose()

    raise RuntimeError("Database did not become ready in time.") from last_error


def run_migrations(
    revision: str,
    *,
    timeout: int,
    poll_interval: float,
    config: Optional[Config] = None,
) -> None:
    config = config or get_alembic_config(str(BACKEND_ROOT / "alembic.ini"))
    database_url = resolve_database_url(config)
    LOGGER.info(
        "Running migrations up to %s (timeout=%ss poll=%ss)",
        revision,
        timeout,
        poll_interval,
    )
    wait_for_database(database_url, timeout=timeout, poll_interval=poll_interval)
    command.upgrade(config, revision)
    LOGGER.info("Migrations complete.")


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=os.getenv("ARCADIA_DB_MIGRATION_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    args = parse_args(argv)
    try:
        config = get_alembic_config(args.config)
        run_migrations(
            args.revision,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Migration run failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
