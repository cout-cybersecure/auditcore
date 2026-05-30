# AuditCore

Read-only **system-discovery and description** platform. AuditCore collects
facts from a target environment using best-in-class tools, normalizes them into
a single schema, and uses specialized AI agents to **strategically and
exhaustively search for information about how the system is built and how it
functions** — then outputs everything it finds in extremely precise factual
detail.

AuditCore **describes**. It does not judge, score, prioritize, or recommend.
There is no risk rating, no remediation blueprint, no verification. The output
is an exhaustive, evidence-backed map of a system's functionality, where every
stated fact cites the evidence it came from.

**Status:** baseline architecture + Phase 1 implementation. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Discovery domains

Security · Performance · Cloud · Kubernetes · Databases · Hardware · Network · Software

## Design principle

Use existing tools (lscpu, hwprobe/hwloc, nmap, osquery, Prometheus, smartctl,
cloud/k8s/db APIs, …) for raw collection. Build proprietary value in
orchestration, normalization, factual extraction (discovery agents), and
precise descriptive reporting.

## Repository layout

```
auditor/
├── ARCHITECTURE.md             # baseline architecture (start here)
├── schemas/                    # generated JSON Schemas (asset, evidence_item,
│                               #   observation, report_section, run)
├── collector/                  # Go collector binary
│   ├── cmd/auditor-collect/    # — entry point
│   ├── internal/{policy,runner}/
│   └── hwprobe/                # — C++ native hardware probe (hwloc + NVML)
├── services/
│   ├── ingestion-api/          # Python/FastAPI — accepts evidence bundles
│   ├── normalizer-worker/      # Rust — concurrent evidence parser
│   ├── model-gateway/          # Python — provider-agnostic AI calls
│   ├── orchestrator/           # discovery workflow (Phase 2)
│   └── report-generator/       # Python — descriptive report renderer
├── packages/
│   ├── models-py/              # Pydantic models + JSON Schema generator
│   └── agents-py/              # agent registry loader
├── agents/                     # 10 agent definitions (discovery + pipeline)
├── connectors/                 # aws / kubernetes / postgres / prometheus
├── policy/                     # OPA allowlist + drift check
├── deploy/                     # docker-compose, helm, terraform
└── docs/                       # ADRs, dev guide
```

## Language choices

| Component | Language | Why |
|---|---|---|
| collector | Go | Single static binary, trivial to drop into a target |
| hwprobe   | C++17 | Direct use of hwloc, NVML, and (optionally) libsensors for hardware fidelity subprocess tools can't reach |
| normalizer-worker | Rust | Concurrent, memory-safe parsing of large evidence sets |
| ingestion-api / model-gateway / report-generator | Python (FastAPI) | I/O-bound, schema-first, fast iteration |
| agents / orchestration | Python | AI ecosystem fit |

## Integrity guarantee

Every observation an agent emits must cite at least one piece of evidence —
enforced in the Pydantic model, the Postgres schema
(`CHECK (array_length(evidence_ids,1) > 0)`), and the orchestrator. Unsourced
output is structurally impossible.

## MVP

Linux host + hardware collection · AWS read · Kubernetes read · Postgres read ·
Prometheus scrape · normalized evidence · evidence-cited observations · technical
+ summary descriptions (HTML/PDF). See [ARCHITECTURE.md](ARCHITECTURE.md#9-first-mvp-scope).

## Future modules

InfraScope (interconnection map) · DriftWatch (factual diff over time) ·
DeepProbe (expanded collectors) · read-only portal · self-hosted edition.
