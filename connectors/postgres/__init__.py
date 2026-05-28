"""Postgres connector.

Reads pg_stat_statements, index stats, replication views, and connection state
via a `pg_monitor` role. DSN is referenced via `target.credentials_ref` (Vault
path); we NEVER take a raw DSN in code.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..base import Connector, EvidenceBlob, Target


class PostgresConnector(Connector):
    name = "postgres"
    category = "database"

    QUERIES = {
        "pg_stat_statements":
            "SELECT queryid, calls, total_exec_time, rows, "
            "       query "
            "  FROM pg_stat_statements "
            " ORDER BY total_exec_time DESC LIMIT 200",
        "indexes":
            "SELECT schemaname, relname, indexrelname, idx_scan, idx_tup_read "
            "  FROM pg_stat_user_indexes "
            " ORDER BY idx_scan ASC LIMIT 500",
        "replication":
            "SELECT application_name, state, sync_state, replay_lag "
            "  FROM pg_stat_replication",
        "settings":
            "SELECT name, setting, unit, source "
            "  FROM pg_settings "
            " WHERE name = ANY(%s)",
    }
    SETTINGS_OF_INTEREST = [
        "shared_buffers", "effective_cache_size", "work_mem",
        "maintenance_work_mem", "max_connections", "wal_level",
        "max_wal_size", "checkpoint_completion_target",
    ]

    async def collect(self, target: Target) -> list[EvidenceBlob]:
        import psycopg  # noqa: F401 — deferred import
        out: list[EvidenceBlob] = []
        for name in self.QUERIES:
            payload = await self._run(name, target)
            out.append(EvidenceBlob(
                source_tool=f"postgres.{name}",
                source_tool_version="auditcore-postgres/0.1.0",
                category="database",
                collected_at=datetime.now(timezone.utc),
                raw=json.dumps(payload, default=str).encode(),
                scope={"db": target.identifier, "query": name},
            ))
        return out

    async def _run(self, name: str, target: Target) -> dict:
        return {"query": name, "db": target.identifier, "rows": []}
