# Phase 21 – Persistence Migration – Automation & Observability

_Status: completed October 15, 2025_

## Highlights

- Automated Alembic migrations via `backend/start.sh`, blocking deploys until schema drift is resolved.
- Added `scripts/run_migrations.py` with readiness checks, configurable timeouts, and retry-aware error handling.
- Introduced `/healthz/database` plus SQLAlchemy pool instrumentation that streams structured telemetry (`db_pool_status`) through the existing logger pipeline.
- Shipped `scripts/db_metrics.py` for on-demand pool snapshots and created a dedicated database recovery runbook.

## Backend changes

- `backend/start.sh` runs migrations (`python -m scripts.run_migrations`) before invoking Uvicorn.
- New `app/db/monitoring.py` instruments the SQLAlchemy engine and exposes `get_pool_snapshot` for health checks and runbooks.
- `app/main.py` now hosts `/healthz/database`, returning pool counters, persistence mode, and proper 503s on failures.
- `app/db/session.py` wires instrumentation into engine initialization; tests cover migration runner, health checks, and telemetry emission.

## Developer workflows

- Environment variables `ARCADIA_DB_MIGRATION_TIMEOUT`, `ARCADIA_DB_MIGRATION_POLL_INTERVAL`, `ARCADIA_DB_MIGRATION_REVISION`, and `ARCADIA_DB_TELEMETRY_INTERVAL` tune migration retries and telemetry cadence.
- New runbook (`docs/runbooks/database-recovery.md`) details backup validation, failover, and rollback procedures.
- `python -m scripts.db_metrics` gives responders a quick JSON snapshot of pool health for incidents or dashboards.

## Follow-ups

- Stream the new `db_pool_status` telemetry into production observability dashboards and alerting.
- Evaluate long-running migration detection (e.g., metrics on average migration duration) once more migrations exist.
- Coordinate with Phase 22 to ensure ELO deduplication and schedule slice telemetry leverage the new health endpoints.
