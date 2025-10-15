"""Emit a one-off snapshot of database pool metrics (Phase 21)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from app.db.monitoring import get_pool_snapshot
from app.db.session import get_engine

LOGGER = logging.getLogger("arcadia.db_metrics")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        snapshot = get_pool_snapshot(engine)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool": snapshot,
        }
        print(json.dumps(payload))
        return 0
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Failed to collect database metrics: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
