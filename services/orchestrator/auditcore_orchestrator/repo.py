"""Persistence layer. A Protocol so the discovery core is testable with a fake,
plus a psycopg implementation for real runs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class EvidenceRow:
    id: UUID
    asset_id: UUID | None
    source_tool: str
    category: str
    parsed: dict[str, Any]


@dataclass(frozen=True)
class AssetRow:
    id: UUID
    type: str
    natural_key: str
    name: str
    attributes: dict[str, Any]


@dataclass
class ObservationWrite:
    run_id: UUID
    asset_id: UUID
    domain: str
    topic: str
    summary: str
    detail: str
    facts: dict[str, Any]
    related_asset_ids: list[UUID]
    evidence_ids: list[UUID]
    produced_by_agent: str
    model_used: str


class Repo(Protocol):
    def evidence_for_category(self, run_id: UUID, category: str) -> list[EvidenceRow]: ...
    def assets_for_run(self, run_id: UUID) -> list[AssetRow]: ...
    def categories_present(self, run_id: UUID) -> list[str]: ...
    def write_observations(self, obs: list[ObservationWrite]) -> int: ...
    def set_run_status(self, run_id: UUID, status: str) -> None: ...
    def audit(self, run_id: UUID, action: str, metadata: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# psycopg implementation
# ---------------------------------------------------------------------------


class PgRepo:
    def __init__(self, dsn: str, tenant_id: UUID) -> None:
        import psycopg  # deferred so importing this module needs no DB driver at rest
        self._psycopg = psycopg
        self._dsn = dsn
        self._tenant_id = tenant_id

    def _conn(self):
        return self._psycopg.connect(self._dsn)

    def categories_present(self, run_id: UUID) -> list[str]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT category FROM evidence_items "
                "WHERE run_id = %s AND parsed IS NOT NULL ORDER BY category",
                (str(run_id),),
            )
            return [r[0] for r in cur.fetchall()]

    def evidence_for_category(self, run_id: UUID, category: str) -> list[EvidenceRow]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT id, asset_id, source_tool, category, parsed "
                "FROM evidence_items "
                "WHERE run_id = %s AND category = %s AND parsed IS NOT NULL "
                "ORDER BY collected_at",
                (str(run_id), category),
            )
            return [
                EvidenceRow(r[0], r[1], r[2], r[3], r[4] or {})
                for r in cur.fetchall()
            ]

    def assets_for_run(self, run_id: UUID) -> list[AssetRow]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT id, type, natural_key, name, attributes "
                "FROM assets WHERE run_id = %s ORDER BY name",
                (str(run_id),),
            )
            return [AssetRow(r[0], r[1], r[2], r[3], r[4] or {}) for r in cur.fetchall()]

    def write_observations(self, obs: list[ObservationWrite]) -> int:
        from psycopg.types.json import Jsonb
        if not obs:
            return 0
        with self._conn() as c, c.cursor() as cur:
            for o in obs:
                cur.execute(
                    """
                    INSERT INTO observations
                        (tenant_id, run_id, asset_id, domain, topic, summary,
                         detail, facts, related_asset_ids, evidence_ids,
                         produced_by_agent, model_used)
                    VALUES (%s, %s, %s, %s::domain, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(self._tenant_id), str(o.run_id), str(o.asset_id),
                        o.domain, o.topic, o.summary, o.detail, Jsonb(o.facts),
                        [str(a) for a in o.related_asset_ids],
                        [str(e) for e in o.evidence_ids],
                        o.produced_by_agent, o.model_used,
                    ),
                )
            c.commit()
        return len(obs)

    def set_run_status(self, run_id: UUID, status: str) -> None:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "UPDATE runs SET status = %s::run_status WHERE id = %s",
                (status, str(run_id)),
            )
            c.commit()

    def audit(self, run_id: UUID, action: str, metadata: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log "
                "(tenant_id, actor, action, resource_type, resource_id, metadata) "
                "VALUES (%s, 'orchestrator', %s, 'run', %s, %s)",
                (str(self._tenant_id), action, str(run_id), Jsonb(metadata)),
            )
            c.commit()
