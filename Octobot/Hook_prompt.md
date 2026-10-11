Reopen Phase 4 Gate 1. Do not mark Phase 4 complete yet.

## Critical fresh-environment schema gap

The migration handles an existing `agentic_artifact_store` table, but a brand-new environment may not have that table when the migration runs.

The Orchestrator's read-only `ArtifactPGStore`:

- Has its own SQLAlchemy model.
- Does not declare `idempotency_key`.
- Calls `create_all()`.
- Can therefore create an incomplete table if Orchestrator starts before Executor.

Executor's later `create_all()` will not add the missing column.

## Required correction

Make fresh-schema creation deterministic regardless of service startup order.

Preferred correction:

- Add the nullable `idempotency_key` column and matching unique index declaration to the Orchestrator's read-only ORM model.
- Match the Executor declaration exactly:
  - Column name
  - Type and length
  - Nullability
  - Uniqueness
  - Index name/convention
- Keep the Orchestrator store read-only at the application level.
- Retain the database-first migration for existing environments.

If mirroring this field is unsafe for a verified code reason, stop and propose removing schema creation ownership from the Orchestrator instead. Do not leave two `create_all()` owners with different table definitions.

## Required schema tests

Cover these scenarios:

1. Existing table without `idempotency_key` receives the column and index.
2. Migration rerun is idempotent.
3. No table exists, migration runs as a no-op, then Executor starts first and creates the complete schema.
4. No table exists, migration runs as a no-op, then Orchestrator starts first and creates the complete schema.
5. Either service starts second and observes the same compatible schema.
6. Old application code continues working against the expanded table.
7. New application code fails predictably if deployed before the required migration against an old table.
8. Executor ORM, Orchestrator ORM, migration SQL, and verification SQL agree on the column and index contract.

Update `db/migrations/README.md` to distinguish:

- Existing environment: migration first, then application deployment.
- Brand-new environment: either service may start first and still create the complete table.
- Rollback limitations once new application code depends on the column.

## Security-sensitive metric tests

Add focused assertions for at least:

- Authorization denied
- Idempotency checksum conflict
- Batch rollback
- Unresolved materialization reference
- Materialization lookup failure

Assert that metric payloads contain safe identifiers and counts only, with no artifact data, row content, tool payload, or exception message.

## Final verification

Re-run:

- Migration contract tests
- Executor full unit suite
- Orchestrator full unit suite
- Gated Postgres integration suite to confirm it remains discoverable and correctly skipped without configuration

Produce a revised go/no-go table that clearly states:

- Unit/code readiness
- Fresh-schema readiness
- Real Postgres integration: BLOCKED until executed
- Kafka/staging integration: BLOCKED until executed
- Security/retention approval: BLOCKED
- Physical cleanup before GA: BLOCKED
- Production enablement: NO-GO
- Narrow internal canary: requires the documented explicit approvals

Do not enable a production use case, create commits, or begin cleanup or AG-UI work. Stop after the corrected Phase 4 report.


The `agentic_artifact_store` table does not currently exist. Extend the Phase 4 correction with a database-first base migration.

## Required work

1. Create:

`db/migrations/000_create_agentic_artifact_store.sql`

2. The migration must:
- Be safely rerunnable.
- Create the configured tenant schema if it does not exist.
- Create `agentic_artifact_store` if it does not exist.
- Match the Executor and Orchestrator SQLAlchemy models exactly.
- Include the nullable `idempotency_key VARCHAR(600)` column from the initial creation.
- Create the unique `ix_agentic_artifact_store_idempotency_key` index.
- Create indexes required by the ORM for tenant, use case, session, and expiry lookup.
- Run transactionally and stop on errors.
- Never drop or replace an existing table.

Use this PostgreSQL definition, adjusting a column only if direct inspection of both ORM models proves the implementation differs:

```sql
BEGIN;

CREATE SCHEMA IF NOT EXISTS :"artifact_schema";

CREATE TABLE IF NOT EXISTS :"artifact_schema".agentic_artifact_store (
    artifact_id        VARCHAR(64) PRIMARY KEY,
    tenant_coin        VARCHAR(255) NOT NULL,
    usecase_id         VARCHAR(255) NOT NULL,
    session_id         VARCHAR(255) NOT NULL,
    invocation_id      VARCHAR(255) NOT NULL,
    runtime_id         VARCHAR(36),
    tool_call_id       VARCHAR(255) NOT NULL,
    tool_name          VARCHAR(255) NOT NULL,

    name               VARCHAR(255) NOT NULL,
    kind               VARCHAR(32) NOT NULL,
    content_type       VARCHAR(128) NOT NULL DEFAULT 'application/json',
    version            INTEGER NOT NULL DEFAULT 1,
    display_order      INTEGER NOT NULL DEFAULT 0,
    row_count          INTEGER,
    size_bytes         INTEGER NOT NULL,
    checksum           VARCHAR(64) NOT NULL,

    data               JSON NOT NULL,
    row_ids            JSON,
    rendering_policy   VARCHAR(32) NOT NULL DEFAULT 'markdown_table',
    authz_scope        JSON NOT NULL,
    source_metadata    JSON,

    idempotency_key    VARCHAR(600),
    created_at         TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at         TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_agentic_artifact_store_tenant_coin
    ON :"artifact_schema".agentic_artifact_store (tenant_coin);

CREATE INDEX IF NOT EXISTS ix_agentic_artifact_store_usecase_id
    ON :"artifact_schema".agentic_artifact_store (usecase_id);

CREATE INDEX IF NOT EXISTS ix_agentic_artifact_store_session_id
    ON :"artifact_schema".agentic_artifact_store (session_id);

CREATE INDEX IF NOT EXISTS ix_agentic_artifact_store_expires_at
    ON :"artifact_schema".agentic_artifact_store (expires_at);

CREATE UNIQUE INDEX IF NOT EXISTS ix_agentic_artifact_store_idempotency_key
    ON :"artifact_schema".agentic_artifact_store (idempotency_key);

COMMIT;
```

Document this execution command in `db/migrations/README.md`:

```bash
psql "$DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -v artifact_schema="$DB_SCHEMA" \
  -f db/migrations/000_create_agentic_artifact_store.sql

psql "$DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -v artifact_schema="$DB_SCHEMA" \
  -f db/migrations/001_add_artifact_idempotency_key.sql
```

The deployment order must be:

1. Run `000_create_agentic_artifact_store.sql`.
2. Run all later migrations, including `001`.
3. Run the verification SQL.
4. Start Orchestration and Executor services.

## Tests

Add contract tests proving:

- The base migration creates every ORM column with compatible types and nullability.
- `idempotency_key` exists on a fresh installation.
- The expected unique index exists.
- Running migration `000` twice is safe.
- Running `001` after `000` is safe.
- Both Executor-first and Orchestrator-first startup see the same complete schema.
- Neither service can create an incomplete version of the table.
- The verification script fails when a required column or index is missing.

Do not enable artifact capture, change production configuration, create commits, or claim real PostgreSQL verification unless the migration is actually executed against PostgreSQL.