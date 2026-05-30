"""Load a run's data from Postgres into a ReportData dataclass."""
from __future__ import annotations

from uuid import UUID

import psycopg

from .render import ReportData


def load_run(dsn: str, run_id: UUID) -> ReportData:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, status, scope, started_at, completed_at, cost_cents "
            "FROM runs WHERE id = %s",
            (str(run_id),),
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError(f"run not found: {run_id}")
        run = {
            "id": str(row[0]), "status": row[1], "scope": row[2],
            "started_at": row[3].isoformat() if row[3] else None,
            "completed_at": row[4].isoformat() if row[4] else None,
            "cost_cents": row[5],
        }

        cur.execute(
            "SELECT id, type, natural_key, name, attributes "
            "FROM assets WHERE run_id = %s ORDER BY name",
            (str(run_id),),
        )
        assets = [
            {"id": str(r[0]), "type": r[1], "natural_key": r[2],
             "name": r[3], "attributes": r[4]}
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT id, asset_id, source_tool, source_tool_version, category, "
            "       parsed, confidence, collected_at "
            "FROM evidence_items WHERE run_id = %s ORDER BY collected_at",
            (str(run_id),),
        )
        evidence = [
            {"id": str(r[0]),
             "asset_id": str(r[1]) if r[1] else None,
             "source_tool": r[2], "source_tool_version": r[3],
             "category": r[4], "parsed": r[5],
             "confidence": r[6],
             "collected_at": r[7].isoformat() if r[7] else None}
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT id, asset_id, domain, topic, summary, detail, facts, "
            "       related_asset_ids, evidence_ids, produced_by_agent "
            "FROM observations WHERE run_id = %s "
            "ORDER BY domain, topic",
            (str(run_id),),
        )
        observations = [
            {"id": str(r[0]), "asset_id": str(r[1]) if r[1] else None,
             "domain": r[2], "topic": r[3], "summary": r[4], "detail": r[5],
             "facts": r[6] or {},
             "related_asset_ids": [str(a) for a in (r[7] or [])],
             "evidence_ids": [str(e) for e in (r[8] or [])],
             "produced_by_agent": r[9]}
            for r in cur.fetchall()
        ]

    return ReportData(
        run=run, assets=assets, evidence=evidence, observations=observations,
    )
