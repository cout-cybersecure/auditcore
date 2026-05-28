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
            "       parsed, severity_hint, confidence, collected_at "
            "FROM evidence_items WHERE run_id = %s ORDER BY collected_at",
            (str(run_id),),
        )
        evidence = [
            {"id": str(r[0]),
             "asset_id": str(r[1]) if r[1] else None,
             "source_tool": r[2], "source_tool_version": r[3],
             "category": r[4], "parsed": r[5],
             "severity_hint": r[6], "confidence": r[7],
             "collected_at": r[8].isoformat() if r[8] else None}
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT id, asset_id, domain, title, description, severity, "
            "       cwe, cve, cis_controls, evidence_ids, produced_by_agent "
            "FROM findings WHERE run_id = %s "
            "ORDER BY CASE severity "
            "  WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "  WHEN 'medium'   THEN 2 WHEN 'low'  THEN 3 ELSE 4 END",
            (str(run_id),),
        )
        findings = [
            {"id": str(r[0]), "asset_id": str(r[1]) if r[1] else None,
             "domain": r[2], "title": r[3], "description": r[4],
             "severity": r[5], "cwe": r[6], "cve": r[7],
             "cis_controls": r[8],
             "evidence_ids": [str(e) for e in (r[9] or [])],
             "produced_by_agent": r[10]}
            for r in cur.fetchall()
        ]

    return ReportData(
        run=run, assets=assets, evidence=evidence,
        findings=findings, blueprints=[],   # blueprints table arrives in Phase 2
    )
