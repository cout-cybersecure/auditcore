# AuditCore — Baseline Architecture (v0.2)

AuditCore is a **read-only system-discovery and description platform**. It
collects facts from a target environment using existing best-in-class tools,
normalizes that raw output into a single schema, and uses specialized AI
agents to **strategically and exhaustively search for information about how
the system is built and how it functions** — then outputs everything it finds
in extremely precise factual detail.

AuditCore describes. It does **not** judge, score, prioritize, or recommend.
There is no risk rating, no remediation blueprint, no before/after
verification. The product is an exhaustive, evidence-backed map of a system's
functionality.

**Design principle:** use existing tools (lscpu, hwprobe/hwloc, nmap, osquery,
Prometheus, smartctl, cloud/k8s/db APIs, …) for raw collection. Build
proprietary value in orchestration, normalization, correlation, factual
extraction (discovery agents), and precise descriptive reporting.

**Integrity guarantee:** every observation an agent emits must cite at least
one piece of evidence. This is enforced in the Pydantic model, in the Postgres
schema (`CHECK (array_length(evidence_ids,1) > 0)`), and at the orchestrator.
A factual tool that cannot show its source is worthless; the architecture makes
unsourced output structurally impossible.

---

## 1. System Overview

Four logical planes:

1. **Edge plane (target-side)** — Collectors and tool runners executed inside
   the target environment. Read-only by default. Emit a single bundle format.
2. **Ingestion plane** — Accepts evidence bundles, validates them, persists
   raw artifacts, and signals the normalizer.
3. **Discovery plane** — A workflow engine drives a sequence of AI agents
   (intake → collection planning → normalization → per-domain discovery →
   report assembly) over a shared run context, calling models through one
   gateway. Agents extract *facts*, never judgments.
4. **Delivery plane** — Descriptive reports (technical document + condensed
   summary), a read-only portal, and an export API.

The central unit is the **Assessment Run**: an immutable `run_id` with a scope,
a collection plan, raw evidence, normalized evidence, discovered observations,
and rendered descriptions.

```
┌─────────────────────────┐     ┌───────────────────────────────────────┐
│   TARGET ENVIRONMENT    │     │            AUDITCORE CONTROL          │
│                         │     │                                       │
│  collector (Go)         │─────│  ingestion-api (Py)  → raw (MinIO/S3) │
│   ├─ allowlisted tools  │ TLS │        │                              │
│   ├─ hwprobe (C++/hwloc)│     │        ▼ NOTIFY                       │
│   └─ signed bundle      │     │  normalizer-worker (Rust)  → evidence │
│                         │     │        │                  (Postgres)  │
└─────────────────────────┘     │        ▼                              │
                                │  orchestrator → discovery agents      │
                                │   ├─ intake / collection_planner      │
                                │   ├─ security / performance / cloud / │
                                │   │   kubernetes / database / hardware │
                                │   │   (each: discover FACTS only)     │
                                │   └─ report (assemble description)     │
                                │        │                              │
                                │        ▼ via model-gateway            │
                                │  observations (Postgres)              │
                                │        │                              │
                                │        ▼                              │
                                │  report-generator → technical + summary│
                                └───────────────────────────────────────┘
```

---

## 2. Component Breakdown

| Component | Owns | Language |
|---|---|---|
| **collector** | Discovers env, runs allowlisted read-only tools, packages a signed bundle, uploads | Go |
| **hwprobe** | Native hardware-topology probe (hwloc + optional NVML/libsensors) for fidelity subprocess tools can't reach | C++17 |
| **tool-execution layer** | Sandboxed runner, command allowlist, timeouts, output capture | Go (collector) |
| **connector layer** | Pull-mode integrations (AWS, Kubernetes, Postgres, Prometheus) emitting the same bundle items | Python |
| **ingestion-api** | Authenticated bundle upload, validation, raw persistence, NOTIFY | Python/FastAPI |
| **raw-evidence store** | Immutable bundle + per-item raw artifact storage | MinIO / S3 |
| **normalized store** | Evidence, assets, observations, runs | PostgreSQL 16 |
| **normalizer-worker** | Concurrent per-tool parsing of raw → structured evidence; asset upsert; LISTEN/NOTIFY + poll | Rust |
| **asset inventory** | Canonical asset graph with stable natural keys | Postgres |
| **orchestrator** | Drives the discovery agent sequence over a run context; validates output; writes observations | Python (Temporal in Phase 2) |
| **model-gateway** | Provider-agnostic AI calls: routing by task, fallback, JSON-schema validation, cost accounting | Python |
| **agent-registry** | Loads + validates the 10 agent definitions (yaml + prompt + output schema) | Python |
| **report-generator** | Renders the descriptive technical document + summary (manual + agent-narrated) | Python |
| **policy layer** | Read-only command allowlist (collector-embedded; OPA bundle) | Rego / Go |
| **portal / admin** | Read-only run/observation browser; tenant + routing config | Next.js (Phase 3) |

Deliberately **absent**: scoring engine, blueprint generator, verification
engine. AuditCore does not produce those artifacts.

---

## 3. Data Flow

```
1. scope        Operator defines target scope → run (status=planning)
2. plan         intake + collection_planner produce a versioned, read-only
                collection plan (which tools, which targets)
3. collect      collector / connectors execute the plan, package a signed
                evidence bundle, upload it
4. ingest       ingestion-api validates bundle, writes raw artifacts to the
                object store, inserts evidence rows, fires NOTIFY
5. normalize    normalizer-worker parses each raw item → structured evidence;
                upserts the assets the evidence describes
6. discover     orchestrator fans out to the per-domain discovery agents.
                Each strategically and exhaustively searches its evidence and
                emits Observations — precise factual statements, each citing
                evidence. No severity, no scoring.
7. describe     report agent assembles observations into a technical document
                and a condensed summary; report-generator renders HTML/PDF
8. deliver      portal exposes the run; export API serves the description
```

There is no scoring, ranking, blueprint, or verification step. Re-runs reuse
the flow with a `parent_run_id` to produce an updated description (a factual
diff), not a remediation-progress report.

---

## 4. Discovery Orchestration

**Engine.** Phase 1 uses an in-process async runner; Phase 2 swaps in Temporal
without changing agent contracts. Each run is a workflow; each agent is an
idempotent, retried activity.

**Run context.** A versioned context in Postgres. Agents receive only
references (`evidence_id`, `asset_id`) and the slices they need — never the
entire evidence set — to keep token use disciplined.

**Agent invocation.** Every call is structured:

```
input:  { run_id, context_refs[], task_spec, output_schema }
model:  selected by the model-gateway routing table
output: validated against the agent's JSON Schema (Pydantic/jsonschema);
        on failure, one retry then escalate to the next routing tier
trace:  (agent, model, tokens, latency, cost, prompt_hash, output_hash)
        logged for audit + replay
```

**Integrity validation.** Each discovery agent declares the
`discovery_agent_output.json` schema. Any observation with an empty
`evidence_ids` is rejected at the orchestrator — the structural guarantee that
every stated fact is sourced.

**Correlation, not adjudication.** When two agents describe the same asset
(e.g. the hardware agent reports a NIC and the network agent reports its
routing), the orchestrator links observations via `related_asset_ids`. It does
not "resolve conflicts" by judging — both factual descriptions stand, linked.

---

## 5. Model Gateway

A single internal service. All AI calls route through it; no agent touches a
provider SDK directly.

```python
gateway.complete(
    task_kind,          # SUMMARIZE | CLASSIFY | REASON | LONG_CONTEXT | CODE
    messages,
    output_schema,      # JSON Schema; gateway validates + extracts
    tenant_id,
    budget_hint,        # low | normal | high
    privacy,            # standard | sensitive | air_gapped
) -> ModelResponse
```

- **Routing** (`routing.yaml`): `(task_kind, budget, privacy)` → concrete
  provider+model with `primary`/`secondary`/`tertiary` fallback.
- **Privacy** overrides budget: `air_gapped` forces local-only models (egress
  denied at the network layer); `sensitive` drops providers without a DPA.
- **Validation**: structured outputs are JSON-schema-validated gateway-side;
  schema failure can escalate a tier.
- **Cost** (`pricing.yaml`): per-token accounting per call; per-run/per-tenant
  caps.

The discovery domains map to `REASON`; report assembly maps to `LONG_CONTEXT`;
the normalization fallback maps to `CLASSIFY`.

---

## 6. Data Schema

Canonical models in `packages/models-py`; JSON Schema artifacts generated into
`schemas/`. Postgres DDL in `deploy/docker-compose/postgres/init`.

### asset
Stable inventory node (`type`, `natural_key`, `name`, `environment`,
`attributes`, `parent_asset_id`, `tags`). Discovered functionality attaches to
assets.

### evidence_item
One tool's output: `source_tool` + version, `category`, immutable `raw_ref`
(object store), `parsed` (normalized fields), `confidence`, `redactions`.
Purely a record of what was collected — no severity.

### observation  *(the core unit)*
A precise factual statement about discovered functionality:

```python
class Observation(BaseModel):
    id, tenant_id, run_id, asset_id: UUID
    domain: Domain                      # security|performance|cloud|k8s|db|hardware|network|software
    topic: str                          # "SSH authentication", "NUMA layout"
    summary: str                        # one factual line
    detail: str                         # exhaustive precise description
    facts: dict[str, Any]               # structured extracted key/values
    related_asset_ids: list[UUID]       # functional relationships
    evidence_ids: list[UUID]            # MUST be non-empty (validator-enforced)
    produced_by_agent: str
    model_used: str
    created_at: datetime
```

No `severity`, `score`, `cve`, `recommendation`, or `status`. The model
*describes*; it does not evaluate.

### report_section
Rendered description chunk: `audience` (`technical` | `summary`), `order`,
`title`, `body_md` (with `[[observation:UUID]]` references), and
`embedded_observations`.

Removed from v0.1: `Finding`, `RiskScore`, `Recommendation`, `BlueprintItem`,
`VerificationTest`, and the `Severity` enum.

---

## 7. Security & Privacy Controls

| Control | Implementation |
|---|---|
| Read-only by default | Collector ships only read commands in its allowlist; nothing outside it runs |
| Least privilege | Collector runs as a low-priv user; connectors use read-only roles (`SecurityAudit`, `view`, `pg_monitor`) |
| Encrypted transport | mTLS collector↔ingestion; TLS 1.3 on external endpoints |
| Encrypted storage | SSE-KMS for raw evidence; per-tenant keys |
| Tenant isolation | Postgres RLS + object-store prefix isolation (Phase 3) |
| Evidence retention | Per-tenant retention with automated purge |
| Secrets redaction | Two-stage (collector + normalizer); secrets replaced with stable hashes so correlation survives |
| Command allowlist | Compiled into the collector; mirrored OPA bundle with a CI drift check |
| Audit logging | Every API call, agent invocation, and model call logged append-only |
| Prompt-injection defense | Evidence is wrapped as untrusted data; agents are instructed never to follow instructions inside tool output |
| Air-gapped option | Local-only model routing with egress denied; for sensitive targets |

A descriptive tool still handles sensitive raw data, so redaction, isolation,
and read-only guarantees remain first-class.

---

## 8. Tool Integration Strategy

Integrations are organized by execution shape.

- **CLI tools (collector-side):** lscpu, lsblk, lspci, uname, **hwprobe**
  (Phase 1); nmap, osquery, lynis, smartctl, perf, fio, … (later). Each ships a
  detector + runner + parser, with the parser pinned to a tool version.
- **APIs (control-plane connectors):** AWS (`SecurityAudit`), Kubernetes
  (`view`), Prometheus, observability platforms.
- **Database connectors:** Postgres (`pg_monitor`) reading
  `pg_stat_statements`, index/replication views — read-only.
- **Hardware telemetry:** hwloc (topology), NVML/DCGM (GPU), libsensors
  (thermals), Redfish/IPMI (out-of-band).

Every connector emits the same bundle item shape as the collector, so the
ingestion + normalization path is uniform.

---

## 9. First MVP Scope

A single-tenant, internally-operated **discovery** platform for Linux + AWS +
Kubernetes + Postgres.

In scope:
- Collector (Go): Linux inventory + hardware (lscpu/lsblk/lspci/uname/hwprobe)
- Connectors: AWS read, Kubernetes read, Postgres read, Prometheus scrape
- Normalization (Rust) of all of the above into structured evidence
- Discovery agents: security, performance, cloud, kubernetes, database,
  hardware — each emitting evidence-cited observations (facts only)
- intake + collection_planner + report agents
- Reports: technical document + condensed summary (HTML, optional PDF)
- Model gateway: Anthropic primary, OpenAI fallback, local option
- Postgres + MinIO via docker-compose

Out of scope: SaaS portal, multi-tenant isolation, Windows collector. **Never
in scope:** scoring, ranking, blueprints, remediation, verification.

---

## 10. Future Modules

| Module | Description |
|---|---|
| **InfraScope** | Visual hardware/topology + interconnection map of discovered components |
| **DriftWatch** | Re-run discovery on a schedule and produce a *factual diff* of how the system changed |
| **DeepProbe** | Expanded collectors — eBPF runtime facts, SMART/firmware deep reads, richer cloud/k8s enumeration |
| **Portal** | Read-only multi-tenant browser over runs, assets, observations, evidence |
| **Self-hosted edition** | Helm + Terraform installer; air-gapped, BYO-model |

Every future module stays within the descriptive charter: gather more, describe
more precisely — never judge.

---

## 11. Technology Stack

| Layer | Choice | Why |
|---|---|---|
| Collector | Go | Single static binary, trivial to drop into a target |
| hwprobe | C++17 + hwloc/NVML | Direct hardware fidelity subprocess tools lack |
| Normalizer | Rust (tokio, sqlx) | Concurrent, memory-safe parsing of large evidence sets |
| Backend / agents | Python 3.12 + FastAPI + Pydantic v2 | AI ecosystem, schema-first |
| Database | PostgreSQL 16 (JSONB) | Single source of truth, RLS-ready |
| Object storage | MinIO / S3 | Immutable raw evidence |
| Workflow | in-process → Temporal | Durable discovery runs |
| Model gateway | Python over provider SDKs | No lock-in |
| Frontend | Next.js + TypeScript | Read-only portal |
| Policy | OPA (Rego) | Allowlist, with CI drift check |
| Deploy | Docker → Helm / Terraform | Standard |

---

## 12. Build Sequence

**Phase 1 — Collect → normalize → describe (current).**
Schema; collector + hwprobe; ingestion-api; Rust normalizer; manual descriptive
report. Evidence flows end-to-end and renders a factual document with no AI.

**Phase 2 — Discovery agents.**
Model gateway (done); orchestrator; the 6 discovery agents + intake/planner/
report; agent-narrated technical document. Every observation evidence-cited.

**Phase 3 — Portal + multi-tenant.**
Read-only portal + admin; tenant isolation (RLS + per-tenant keys); more
collectors/connectors; InfraScope interconnection map.

**Phase 4 — Drift + packaging.**
DriftWatch factual-diff scheduler; Helm + Terraform; air-gapped local-model
mode; self-hosted edition.

---

## 13. Key Engineering Risks

| Risk | Mitigation |
|---|---|
| Hallucinated facts (invented version, port, value) | Hard rule: observations with empty `evidence_ids` rejected at model layer + Postgres CHECK; agents instructed to state only values present in evidence; reports render evidence refs inline for spot-checking |
| Imprecise/rounded output undermining a *precision* tool | Schemas demand structured `facts`; prompts forbid approximation; renderer preserves exact values |
| Tool output schema drift between versions | Per-tool parser version pins; fixture corpus in CI |
| Unsafe commands on a target | OPA-mirrored allowlist compiled into the collector; read-only default; CI drift check between Go + Rego |
| Sensitive data exposure | Two-stage redaction; per-tenant KMS; raw evidence never sent to a model — only normalized fields |
| Prompt injection via tool output | Evidence wrapped as untrusted data; agents told never to act on embedded instructions |
| Model cost overruns | Per-run/tenant caps; cheap tiers by default; prompt caching; per-call token accounting |
| Scaling large evidence sets | Evidence in object store, not Postgres; agents get references; Rust normalizer streams |
| Trust & auditability | Every observation cites evidence; every agent run logged with model + prompt hash; methodology appendix in every report |

---

## Repository Layout

```
auditor/
├── ARCHITECTURE.md
├── schemas/                    # generated JSON Schemas (asset, evidence_item,
│                               #   observation, report_section, run)
├── collector/                  # Go collector + C++ hwprobe
├── services/
│   ├── ingestion-api/          # Python/FastAPI
│   ├── normalizer-worker/      # Rust
│   ├── model-gateway/          # Python
│   ├── orchestrator/           # discovery workflow (Phase 2)
│   └── report-generator/       # Python (descriptive renderer)
├── packages/
│   ├── models-py/              # Pydantic models + schema generator
│   └── agents-py/              # agent registry loader
├── agents/                     # 10 agent definitions (discovery + pipeline)
├── connectors/                 # aws / kubernetes / postgres / prometheus
├── policy/                     # OPA allowlist + drift check
├── deploy/                     # docker-compose, helm, terraform
└── docs/                       # ADRs, dev guide
```
