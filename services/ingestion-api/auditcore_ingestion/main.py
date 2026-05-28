from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from . import bundle as bundle_mod
from . import storage
from .config import settings
from .db import close_pool, conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("auditcore.ingestion")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Touch the storage client to ensure the bucket exists at startup.
    storage.client()
    yield
    close_pool()


app = FastAPI(title="AuditCore Ingestion API", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateRunRequest(BaseModel):
    scope: dict[str, Any] = {}


class CreateRunResponse(BaseModel):
    run_id: UUID
    status: str


class IngestResponse(BaseModel):
    run_id: UUID
    accepted_items: int
    status: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/runs", response_model=CreateRunResponse, status_code=status.HTTP_201_CREATED)
def create_run(body: CreateRunRequest) -> CreateRunResponse:
    tenant_id = settings.default_tenant_id
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO runs (tenant_id, scope, status)
            VALUES (%s, %s, 'collecting')
            RETURNING id, status
            """,
            (tenant_id, Jsonb(body.scope)),
        )
        run_id, run_status = cur.fetchone()
        _audit(cur, tenant_id, "system", "run.create", "run", str(run_id))
        c.commit()
    return CreateRunResponse(run_id=run_id, status=run_status)


@app.post("/v1/runs/{run_id}/bundle", response_model=IngestResponse)
async def ingest_bundle(run_id: UUID, bundle_file: UploadFile) -> IngestResponse:
    data = await bundle_file.read()
    if len(data) > settings.max_bundle_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "bundle too large")

    try:
        b = bundle_mod.parse_bundle(data)
    except bundle_mod.BundleError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid bundle: {e}") from e

    tenant_id = settings.default_tenant_id

    # 1. Persist the raw tarball.
    bundle_key = f"runs/{run_id}/bundles/{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
    storage.put_bytes(bundle_key, data, content_type="application/gzip")

    # 2. Persist each item's raw bytes and write evidence_items rows.
    inserted = 0
    with conn() as c, c.cursor() as cur:
        # Ensure the run exists.
        cur.execute("SELECT 1 FROM runs WHERE id = %s AND tenant_id = %s",
                    (str(run_id), tenant_id))
        if cur.fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")

        for item in b.items:
            key = f"runs/{run_id}/items/{item.id}.raw"
            raw_ref = storage.put_bytes(key, item.raw_bytes)

            cur.execute(
                """
                INSERT INTO evidence_items
                    (id, tenant_id, run_id, source_tool, source_tool_version,
                     collected_at, category, raw_ref, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    str(item.id),
                    tenant_id,
                    str(run_id),
                    item.source_tool,
                    item.source_tool_version,
                    item.collected_at,
                    item.category,
                    raw_ref,
                    0.0,  # placeholder; parser overwrites
                ),
            )
            inserted += cur.rowcount

        cur.execute(
            "UPDATE runs SET status = 'normalizing' WHERE id = %s",
            (str(run_id),),
        )
        _audit(cur, tenant_id, "collector", "bundle.ingest", "run", str(run_id),
               {"items": len(b.items), "bundle_key": bundle_key})
        c.commit()

    # The Postgres `evidence_items_notify` trigger fires NOTIFY
    # auditcore_evidence_ready, which the Rust normalizer-worker is listening
    # on. We never normalize inline from the API anymore.
    return IngestResponse(run_id=run_id, accepted_items=inserted, status="normalizing")


@app.get("/v1/runs/{run_id}")
def get_run(run_id: UUID) -> JSONResponse:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT id, status, scope, started_at, completed_at, cost_cents
              FROM runs WHERE id = %s
            """,
            (str(run_id),),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
        cur.execute(
            "SELECT COUNT(*) FROM evidence_items WHERE run_id = %s",
            (str(run_id),),
        )
        evidence_count = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM evidence_items WHERE run_id = %s AND parsed IS NOT NULL",
            (str(run_id),),
        )
        normalized_count = cur.fetchone()[0]

    return JSONResponse({
        "id": str(row[0]),
        "status": row[1],
        "scope": row[2],
        "started_at": row[3].isoformat() if row[3] else None,
        "completed_at": row[4].isoformat() if row[4] else None,
        "cost_cents": row[5],
        "evidence_count": evidence_count,
        "normalized_count": normalized_count,
    })


@app.get("/v1/runs/{run_id}/evidence")
def list_evidence(run_id: UUID) -> JSONResponse:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT id, asset_id, source_tool, source_tool_version, category,
                   raw_ref, parsed, severity_hint, confidence, collected_at
              FROM evidence_items
             WHERE run_id = %s
             ORDER BY collected_at
            """,
            (str(run_id),),
        )
        items = [
            {
                "id": str(r[0]),
                "asset_id": str(r[1]) if r[1] else None,
                "source_tool": r[2],
                "source_tool_version": r[3],
                "category": r[4],
                "raw_ref": r[5],
                "parsed": r[6],
                "severity_hint": r[7],
                "confidence": r[8],
                "collected_at": r[9].isoformat(),
            }
            for r in cur.fetchall()
        ]
    return JSONResponse({"run_id": str(run_id), "items": items})


@app.get("/v1/runs/{run_id}/assets")
def list_assets(run_id: UUID) -> JSONResponse:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT id, type, natural_key, name, attributes, first_seen, last_seen
              FROM assets WHERE run_id = %s
            """,
            (str(run_id),),
        )
        assets = [
            {
                "id": str(r[0]),
                "type": r[1],
                "natural_key": r[2],
                "name": r[3],
                "attributes": r[4],
                "first_seen": r[5].isoformat(),
                "last_seen": r[6].isoformat(),
            }
            for r in cur.fetchall()
        ]
    return JSONResponse({"run_id": str(run_id), "assets": assets})


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _audit(cur, tenant_id: str, actor: str, action: str,
           resource_type: str, resource_id: str,
           metadata: dict | None = None) -> None:
    cur.execute(
        """
        INSERT INTO audit_log (tenant_id, actor, action, resource_type, resource_id, metadata)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (tenant_id, actor, action, resource_type, resource_id, Jsonb(metadata or {})),
    )
