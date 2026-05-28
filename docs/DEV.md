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

The flow:
1. Collector (Go) runs allowlisted tools including `hwprobe` (C++/hwloc).
2. Bundle uploads to `ingestion-api` (Python/FastAPI). Raw bytes land in MinIO; rows in Postgres.
3. Trigger fires `NOTIFY auditcore_evidence_ready <run_id>`.
4. `normalizer-worker` (Rust) wakes, fetches raw from MinIO, runs the per-tool parser, writes `parsed` JSONB and upserts assets.

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
