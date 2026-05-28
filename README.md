# AuditCore

Multi-agent technical assessment platform. Collects facts from client environments using best-in-class OSS and commercial tools, normalizes them into a single schema, applies specialized AI agents to interpret findings, ranks risk, generates target-state blueprints, verifies remediation, and produces engineer- and executive-facing reports.

**Status:** baseline architecture only. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Domains covered

Security · Cloud · Kubernetes · Performance · Databases · Hardware

## Design principle

Use existing tools (Nmap, Trivy, Prowler, Prometheus, perf, smartctl, etc.) for raw collection. Build proprietary value in orchestration, normalization, AI interpretation, prioritization, blueprint generation, verification, and reporting.

## Repository layout

```
auditor/
├── ARCHITECTURE.md             # baseline architecture (start here)
├── schemas/                    # canonical data models (Pydantic + JSON Schema)
├── collector/                  # Go collector binary
│   ├── cmd/auditor-collect/    # — entry point
│   ├── internal/{policy,runner}/
│   └── hwprobe/                # — C++ native hardware probe (hwloc + NVML)
├── services/
│   ├── ingestion-api/          # Python/FastAPI — accepts evidence bundles
│   └── normalizer-worker/      # Rust — concurrent evidence parser
├── packages/models-py/         # Pydantic schemas (Python)
├── agents/                     # AI agent definitions, prompts, output schemas
├── connectors/                 # cloud / k8s / db / observability integrations
├── blueprints/                 # target-state templates
├── frontend/                   # Next.js portal
├── deploy/                     # docker-compose, helm, terraform
└── docs/                       # ADRs, runbooks
```

## Language choices

| Component | Language | Why |
|---|---|---|
| collector | Go | Single static binary, trivial to drop into client environments |
| hwprobe   | C++17 | Direct use of hwloc, NVML, and (optionally) libsensors for hardware fidelity that subprocess tools can't reach |
| normalizer-worker | Rust | Concurrent, memory-safe parsing of large evidence bundles at scale |
| ingestion-api | Python (FastAPI) | I/O-bound, schema-first, fast iteration |
| agents / orchestration | Python | AI ecosystem fit |

## MVP

Linux host collection · AWS posture · Kubernetes scan ingestion · vulnerability scan ingestion · performance metrics ingestion · hardware inventory · risk ranking · blueprint generation · PDF/HTML reports. See [ARCHITECTURE.md](ARCHITECTURE.md#9-first-mvp-scope).

## Future modules

DriftGuard · PerfLens · InfraScope · ProofPack · client SaaS portal · self-hosted enterprise edition.
