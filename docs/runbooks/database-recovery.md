# Database Recovery & Failover Runbook

_Status: drafted October 15, 2025 (Phase 21)_

This runbook captures the on-call workflow for handling Arcadia Coach database incidents after the PostgreSQL migration. Keep it updated as Render infrastructure and tooling evolve.

## 1. Pre-flight Checklist

- Confirm the currently deployed hash and persistence mode (`ARCADIA_PERSISTENCE_MODE`) from Render dashboard.
- Verify the migration runner history in deploy logs (`python -m scripts.run_migrations`). Any non-zero exit halts the deploy and requires investigation before proceeding.
- Capture an on-demand pool snapshot:
  ```bash
  cd backend
  python -m scripts.db_metrics
  ```
  Attach the JSON payload to the incident ticket for historical context.

## 2. Backup Validation

1. Trigger an ad-hoc logical backup:
   ```bash
   pg_dump "$ARCADIA_DATABASE_URL" --format=custom --file=arcadia-$(date +%Y%m%d%H%M).dump
   ```
2. Immediately restore into a local container or staging instance to confirm integrity:
   ```bash
   createdb arcadia-restore
   pg_restore --dbname=arcadia-restore arcadia-*.dump
   ```
3. Document success/failure, elapsed time, and dump size in the incident log.

## 3. Failover & Connection Rotation

1. Promote the warm standby (see Render playbook) or create a new managed instance from the latest backup.
2. Update `ARCADIA_DATABASE_URL` for backend and MCP services. Prefer Render secrets; avoid editing `render.yaml` directly for emergency rotations.
3. Redeploy both services. The startup script runs migrations automatically and blocks on schema drift—watch for successful “Migrations complete.” logs.
4. Verify `/healthz/database` returns `200` in production. A `503` indicates lingering connectivity or authentication errors.

## 4. Rollback Strategy

- If migrations introduced the regression, roll back to the previous container image and set `ARCADIA_DB_MIGRATION_REVISION` to the prior migration before redeploying.
- Confirm the migration runner exits cleanly with the override revision, then remove the override once the hotfix ships.
- When operating in `hybrid` persistence mode, ensure legacy JSON stores remain untouched to prevent data duplication.

## 5. Post-incident Actions

- Backfill missed telemetry to the analytics warehouse using `scripts/db_metrics.py` snapshots captured during the incident.
- File follow-up issues for any manual steps that can be automated (e.g., promoting replicas, verifying backups).
- Update this runbook with new learnings, including command snippets, gotchas, or revised SLAs.

For escalations, contact the Platform & Infrastructure owner listed in `docs/current-issues.md`.
