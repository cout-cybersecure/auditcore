# Dev quickstart

## Prerequisites
- Docker + docker-compose
- Python 3.12 (with [uv](https://github.com/astral-sh/uv) recommended) — ingestion-api
- Go 1.22+ — collector
- Rust 1.75+ (cargo) — normalizer-worker
- CMake 3.16+, g++ ≥ 9, `libhwloc-dev` — C++ hwprobe
  - Optional: `libsensors4-dev` for thermals, `nvidia-ml-dev` for NVIDIA GPU inventory
- Linux host with `lscpu`, `lsblk`, `lspci`, `uname` for the basic collector profile

## One-shot bring-up

```bash
make infra-up          # Postgres on :5432, MinIO on :9000 + console :9001
make api-install
make api-run           # serves on :8000 — leave running in one terminal
make normalizer-run    # second terminal: Rust worker (LISTENs + polls)
make e2e-smoke         # third terminal: build collector + hwprobe + upload
```

The pipeline — collect → normalize → discover → describe:
1. Collector (Go) runs allowlisted read-only tools incl. `hwprobe` (C++/hwloc), `ip`, `ss`.
2. Bundle uploads to `ingestion-api` (Python/FastAPI). Raw bytes land in MinIO; rows in Postgres.
3. Trigger fires `NOTIFY auditcore_evidence_ready <run_id>`.
4. `normalizer-worker` (Rust) wakes, fetches raw from MinIO, runs the per-tool parser, writes `parsed` JSONB and upserts assets.
5. `orchestrator` (Python) runs the discovery agents over the run's evidence and writes **observations** — precise factual statements, each citing evidence. Needs the `model-gateway` running.
6. `report-generator` (Python) renders the observations into a descriptive document.

AuditCore describes what it finds; it never scores, ranks, or recommends.

## Discover + describe

```bash
# model-gateway (set a provider key, e.g. AUDITCORE_GATEWAY_ANTHROPIC_API_KEY)
make gateway-run                                   # serves on :8001

# run the discovery agents over a normalized run, writing observations
auditcore-discover run <run-id>

# render the descriptive document (purely factual, no AI) from the DB
auditcore-report render <run-id> --audience technical --out description.html
auditcore-report render <run-id> --audience summary   --out summary.html
```

The orchestrator enforces the integrity guard: any observation that cites no
evidence, cites evidence it was not given, or references a foreign asset is
dropped with a recorded reason. Every persisted observation is sourced.

Inspect the run:

```bash
curl -s http://localhost:8000/v1/runs        # not implemented yet (single-run mode)
curl -s http://localhost:8000/v1/runs/<run-id>            | jq
curl -s http://localhost:8000/v1/runs/<run-id>/evidence   | jq
curl -s http://localhost:8000/v1/runs/<run-id>/assets     | jq
```

The collector prints the `run_id` it created. The MinIO console (http://localhost:9001, login `auditcore` / `dev-only-change-me`) shows raw evidence under `auditcore-raw-evidence/runs/<run-id>/`.

## Database access

```bash
make psql
\dt              # tables
SELECT id, status, started_at FROM runs ORDER BY started_at DESC LIMIT 5;
SELECT source_tool, confidence, parsed->>'Model name' FROM evidence_items;
```

## Offline collector mode (no network egress)

```bash
make collector-build
./bin/auditor-collect run --output /tmp/bundle.tar.gz
# transfer bundle.tar.gz to a host with network access, then:
curl -X POST http://localhost:8000/v1/runs -H 'Content-Type: application/json' -d '{}'
# take the returned run_id, then:
curl -X POST http://localhost:8000/v1/runs/<run-id>/bundle \
     -F "bundle_file=@/tmp/bundle.tar.gz"
```

## Resetting state

```bash
make infra-nuke        # wipes Postgres + MinIO volumes
```
