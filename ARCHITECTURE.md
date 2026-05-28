# AuditCore — Baseline Architecture (v0.1)

AuditCore is a multi-agent technical assessment platform. It collects facts from client environments using existing best-in-class tools, normalizes the output into a single schema, applies specialized AI agents to interpret findings, ranks risk, generates target-state blueprints, verifies remediation, and produces both engineer- and executive-facing reports.

This document is the baseline architecture. It is intended to be the source a senior engineer uses to lay down the repository, schemas, API boundaries, and first collector prototype.

**Design principle:** Buy (or use OSS) the raw scanning, profiling, and telemetry layer. Build proprietary value in orchestration, normalization, correlation, AI interpretation, prioritization, blueprint generation, verification, and reporting.

---

## 1. System Overview

AuditCore is structured as four logical planes:

1. **Edge plane (client-side)** — Collectors and tool runners deployed inside the client environment. Read-only by default. Speak a single ingestion protocol back to the control plane.
2. **Ingestion plane** — Accepts uploaded evidence bundles, validates them, persists raw artifacts, and writes them to a normalization queue.
3. **Analysis plane** — Workflow engine drives a DAG of AI agents (intake → planner → normalization → domain analysis → risk → blueprint → verification → report) over a shared run context. Talks to AI models through a single gateway.
4. **Delivery plane** — Client portal, admin console, report rendering, API for export and integrations (Slack, Jira, ServiceNow, S3).

A single conceptual unit is the **Assessment Run**. Every run has an immutable `run_id`, a scope, a versioned collection plan, raw evidence, normalized findings, an agent trace, scored risks, blueprints, and rendered reports.

```
┌─────────────────────────┐      ┌──────────────────────────────────────┐
│   CLIENT ENVIRONMENT    │      │            AUDITCORE CONTROL          │
│                         │      │                                       │
│  collector-cli (Go)     │──────│  ingestion-api  →  raw evidence (S3)  │
│   ├─ runs allowlisted   │ TLS  │        │                              │
│   │   tools             │ mTLS │        ▼                              │
│   ├─ packages bundle    │      │  normalizer-worker  →  findings (PG)  │
│   └─ uploads bundle     │      │        │                              │
│                         │      │        ▼                              │
└─────────────────────────┘      │  agent-orchestrator (Temporal)        │
                                 │   ├─ Intake / Planner                 │
                                 │   ├─ Domain agents (Sec/Perf/Cloud/   │
                                 │   │   K8s/DB/HW)                      │
                                 │   ├─ RiskRank                         │
                                 │   ├─ Blueprint                        │
                                 │   ├─ Verification                     │
                                 │   └─ Report                           │
                                 │              │                        │
                                 │              ▼                        │
                                 │  model-gateway → OpenAI/Anthropic/    │
                                 │                  Google/Local         │
                                 │              │                        │
                                 │              ▼                        │
                                 │  reports (PDF/HTML) → portal + API    │
                                 └──────────────────────────────────────┘
```

---

## 2. Component Breakdown

| Component | Owns | Tech (recommended) |
|---|---|---|
| **collector-cli** | Discovers env, plans safe commands, runs allowlisted tools, packages signed evidence bundle, uploads | Go (single static binary) |
| **tool-execution-layer** | Sandboxed subprocess runner, command allowlist, timeouts, output capture, redaction | Go inside collector; Python wrapper in control plane for re-runs |
| **connector-layer** | Pull-mode integrations (AWS/GCP/Azure APIs, Kubernetes API, DB connectors, Prometheus, Grafana, vendor SaaS) | Python (async) |
| **ingestion-api** | Authenticated bundle upload, schema validation, deduplication, write to object store + queue | FastAPI |
| **raw-evidence-store** | Immutable bundle storage, per-tenant prefix, server-side encryption | S3-compatible (AWS S3 / MinIO) |
| **normalized-findings-store** | Structured findings, evidence, assets, runs | PostgreSQL 16 (JSONB for evidence payloads) |
| **asset-inventory** | Canonical asset graph (hosts, containers, cloud resources, DBs, GPUs) with stable IDs | Postgres + materialized views |
| **search-index** | Full-text and faceted search across findings and assets | OpenSearch |
| **ai-orchestration-layer** | Workflow engine, agent registry, run context, retries, idempotency | Temporal |
| **model-gateway** | Provider abstraction, routing, cost/latency accounting, fallback, prompt cache | Python service wrapping LiteLLM + custom router |
| **agent-registry** | Agent definitions, prompts, tools, schema bindings, version pinning | YAML in repo + Postgres rows for runtime config |
| **policy-and-permission-layer** | Command allowlists, scope guards, data residency rules, action approval | Open Policy Agent (Rego) |
| **scoring-engine** | Deterministic risk scoring with AI-assisted weighting | Python service |
| **blueprint-generator** | Target-state architecture artifacts (HCL/YAML/Markdown), idempotent IaC suggestions | Python + Jinja templates |
| **verification-engine** | Defines and runs before/after tests, computes deltas | Python; re-uses collector + checkers |
| **report-generator** | Executive PDF + engineer HTML/Markdown, evidence-linked | Python (WeasyPrint) + React renderer for HTML |
| **client-portal** | Tenant-facing UI: runs, findings, blueprints, reports, exports | Next.js + TypeScript + shadcn/ui |
| **admin-console** | Tenant mgmt, model routing config, agent versions, audit log viewer | Same Next.js app, role-gated |

---

## 3. Data Flow

The canonical flow for a single Assessment Run:

```
1. scope:           Client scope defined in portal or via API
                    → creates run record (status=planning)
2. plan:            Intake Agent + Collection Planner produce a versioned
                    collection plan (which tools, which targets, which
                    permissions) → persisted to runs.collection_plan
3. execution:       collector-cli (or connectors) executes plan in client
                    env, packages evidence bundle, signs it, uploads
4. ingest:          ingestion-api validates bundle signature + schema,
                    writes raw artifacts to S3, enqueues normalize task
5. normalize:       Evidence Normalization Agent + per-tool parsers
                    convert raw output → evidence_items (typed), tag
                    with asset_id, severity hint, source_tool, confidence
6. analyze:         RiskRank-aware fan-out to domain agents (Security,
                    Performance, Cloud, K8s, DB, Hardware). Each writes
                    findings + recommendations referencing evidence_items
7. score:           RiskRank Agent assigns final priority using exposure,
                    exploitability, asset importance, blast radius,
                    business impact, fix difficulty, confidence
8. blueprint:       Blueprint Agent emits target-state artifacts per
                    domain (hardening profile, perf budget, cloud module,
                    K8s manifests, DB tuning, HW topology)
9. verify-plan:     Verification Agent defines pre/post tests tied to
                    each remediation
10. report:         Report Agent renders exec + engineer reports, links
                    every claim to evidence_items
11. deliver:        Portal exposes run; webhooks fire to Slack/Jira/etc.
```

Re-runs and verification runs reuse the same flow but with `parent_run_id` and a delta-only report.

---

## 4. AI Orchestration Plan

**Engine.** Temporal. Each Assessment Run is a Temporal workflow. Each agent is an activity (or a child workflow when it itself fans out). Activities are idempotent, retried with exponential backoff, and durably checkpointed so a half-completed run survives restarts.

**Run context.** A shared, versioned `RunContext` object lives in Postgres and is referenced by every agent. Agents do not pass large blobs between themselves — they pass references (`evidence_item_id`, `finding_id`, `asset_id`). The orchestrator hydrates context per agent invocation with only the slice that agent needs (token discipline).

**Agent invocation pattern.** Every agent call is structured:

```
input:  { run_id, context_refs[], task_spec, output_schema }
model:  selected by model-gateway routing
output: validated against output_schema (Pydantic), rejected on schema
        failure with one retry, then escalated to a stronger model
trace:  every call logged with (agent, model, tokens, latency, cost,
        prompt_hash, output_hash) for audit + replay
```

**Output validation.** Every agent declares a strict JSON Schema (Pydantic model) for its output. Outputs that fail validation are retried once at the same model, then escalated to the next tier. Findings without an evidence reference are rejected at the orchestrator level — this is the primary hallucination guard.

**Conflict resolution.** When two domain agents disagree (e.g., Security Agent calls a port exposure critical, Cloud Agent says it's intentionally public via WAF), the orchestrator triggers a **Reconciliation Step**:

1. Both findings tagged `in_conflict`.
2. Reconciler agent (stronger reasoning model, long context) receives both findings + all referenced evidence + asset metadata.
3. Emits either a merged finding, an override (with rationale), or marks `unresolved_conflict=true` for human review.

**Critic loop (optional, costed).** Domain agent outputs can optionally pass through a Critic Agent that checks: (a) every claim cites evidence, (b) recommendation is technically valid, (c) severity is justified. Enabled per-tenant or per-domain based on tier.

**Human-in-the-loop gates.** Configurable per tenant: pause workflow before report delivery for human review of CRITICAL findings.

---

## 5. Model Gateway Design

A single internal service. All AI calls go through it. No agent ever instantiates a provider SDK directly.

**Interface (Python, simplified):**

```python
class ModelGateway:
    async def complete(
        self,
        task_kind: TaskKind,           # SUMMARIZE | CLASSIFY | REASON | LONG_CONTEXT | CODE
        messages: list[Message],
        output_schema: type[BaseModel] | None = None,
        tenant_id: str,
        budget_hint: BudgetTier = "normal",
        privacy: PrivacyTier = "standard",  # standard | sensitive | air_gapped
    ) -> ModelResponse: ...
```

**Routing table (default).** The gateway resolves `(task_kind, budget_hint, privacy)` to a concrete provider+model via a routing table that lives in Postgres and is editable per tenant.

| task_kind | budget=low | budget=normal | budget=high | privacy=air_gapped |
|---|---|---|---|---|
| SUMMARIZE | Haiku / GPT-4.1-mini / Gemini Flash | Haiku | Sonnet | Llama-3.1-70B local |
| CLASSIFY | small local / Haiku | Haiku | Sonnet | Llama-3.1-8B local |
| REASON | Sonnet | Opus / GPT-5 / Gemini Pro | Opus + critic loop | Llama-3.1-70B local |
| LONG_CONTEXT | Sonnet | Sonnet 200k / Gemini 1M | Opus 200k | Llama-3.1-70B w/ chunking |
| CODE | Sonnet | Sonnet | Opus | DeepSeek-Coder / Llama local |

**Fallback.** Routing table defines `primary`, `secondary`, `tertiary` per slot. On provider error or rate-limit, gateway transparently fails over. After N consecutive failures, marks primary `unhealthy` for cooldown window.

**Privacy.** `privacy=sensitive` forces a provider with a signed DPA and zero-retention setting. `privacy=air_gapped` forces local-only models (no egress allowed; egress is enforced at the network policy layer, not just config).

**Cost control.** Per-tenant monthly cap, per-run soft cap with warning, hard cap with graceful degradation (drop to cheaper tier and flag the report). All token counts and dollar amounts logged per agent call for cost attribution.

**Prompt cache.** Provider-native prompt caching (Anthropic, OpenAI) used aggressively for static agent system prompts and large evidence prefixes.

**Wire format.** Gateway speaks OpenAI-compatible chat format internally and translates per provider via LiteLLM. Tool-use / structured outputs are normalized to JSON Schema validation on the gateway side, so agents see a uniform contract.

---

## 6. Data Schema Proposal

First-draft Pydantic / JSON Schema models. Stored in Postgres; large blobs in S3.

### asset

```python
class Asset(BaseModel):
    id: UUID
    tenant_id: UUID
    run_id: UUID                       # first run that discovered it
    type: Literal[
        "host", "vm", "container", "pod", "k8s_node", "k8s_cluster",
        "cloud_account", "cloud_resource", "database", "gpu",
        "network_device", "load_balancer", "storage_bucket"
    ]
    natural_key: str                   # provider+region+resource_id or hostname+uuid
    name: str
    environment: Literal["prod", "staging", "dev", "unknown"]
    importance: int = 3                # 1-5, derived or user-set
    attributes: dict[str, Any]         # type-specific (os, kernel, cpu_model, ...)
    parent_asset_id: UUID | None       # e.g. pod → node, container → host
    tags: dict[str, str]
    first_seen: datetime
    last_seen: datetime
```

### evidence_item

```python
class EvidenceItem(BaseModel):
    id: UUID
    tenant_id: UUID
    run_id: UUID
    asset_id: UUID | None              # may be null if asset not yet resolved
    source_tool: str                   # "nmap", "trivy", "prowler", ...
    source_tool_version: str
    collected_at: datetime
    category: Literal[
        "security", "performance", "cloud", "kubernetes",
        "database", "hardware", "inventory"
    ]
    raw_ref: str                       # S3 URI to original output
    parsed: dict[str, Any]             # normalized fields per tool parser
    severity_hint: Literal["info","low","medium","high","critical"] | None
    confidence: float                  # 0.0-1.0, parser confidence
    redactions: list[str] = []         # list of redaction rule ids applied
```

### finding

```python
class Finding(BaseModel):
    id: UUID
    tenant_id: UUID
    run_id: UUID
    asset_id: UUID
    domain: Literal["security","performance","cloud","k8s","db","hardware"]
    title: str                         # short, human
    description: str                   # long, explains the issue + impact
    severity: Literal["info","low","medium","high","critical"]
    cwe: list[str] = []                # if applicable
    cve: list[str] = []
    cis_controls: list[str] = []
    evidence_ids: list[UUID]           # MUST be non-empty
    produced_by_agent: str             # agent name + version
    model_used: str
    status: Literal["open","accepted_risk","fixed","false_positive","in_conflict"]
    created_at: datetime
```

### risk_score

```python
class RiskScore(BaseModel):
    finding_id: UUID
    exposure: int                      # 0-10
    exploitability: int                # 0-10
    asset_importance: int              # 1-5
    blast_radius: int                  # 0-10
    business_impact: int               # 0-10
    fix_difficulty: int                # 1-5 (5 = hard)
    confidence: float                  # 0.0-1.0
    composite: float                   # weighted sum, 0-100
    rank: int                          # 1 = top priority within run
    rationale: str                     # 1-3 sentences, AI-written
    scored_by_agent: str
```

### recommendation

```python
class Recommendation(BaseModel):
    id: UUID
    finding_id: UUID
    summary: str
    steps: list[str]                   # ordered, imperative
    automation_available: bool
    automation_ref: str | None         # path to blueprint_item or runbook
    effort_estimate: Literal["minutes","hours","days","weeks"]
    blast_radius: Literal["isolated","service","tenant","global"]
    requires_change_window: bool
    rollback_plan: str
```

### blueprint_item

```python
class BlueprintItem(BaseModel):
    id: UUID
    run_id: UUID
    domain: Literal["security","performance","cloud","k8s","db","hardware"]
    target: str                        # e.g. "aws-vpc-baseline", "pg-tuning-oltp"
    format: Literal["terraform","helm","kustomize","ansible","sql","markdown","yaml"]
    artifact_ref: str                  # S3 URI
    sources: list[UUID]                # finding_ids that motivated this
    applies_to_assets: list[UUID]
    idempotent: bool
    review_required: bool
```

### verification_test

```python
class VerificationTest(BaseModel):
    id: UUID
    finding_id: UUID
    name: str
    kind: Literal["command","scan","metric_check","query"]
    spec: dict[str, Any]               # command + expected, or scan rule, etc.
    baseline_result: dict | None       # captured at first run
    post_result: dict | None           # captured at verification run
    passed: bool | None
    delta_summary: str | None
```

### report_section

```python
class ReportSection(BaseModel):
    id: UUID
    run_id: UUID
    audience: Literal["executive","engineer"]
    order: int
    title: str
    body_md: str                       # markdown, evidence refs as [[evidence:UUID]]
    embedded_findings: list[UUID]
    embedded_blueprints: list[UUID]
```

---

## 7. Security and Privacy Controls

| Control | Implementation |
|---|---|
| Read-only default | Collectors only ship with read commands in their allowlist. Write operations require a separately-signed write profile and explicit per-run authorization. |
| Least privilege | Collector runs as a dedicated low-privilege user. Cloud connectors use scoped read-only roles (`SecurityAudit` on AWS, equivalent on GCP/Azure). |
| Encrypted transport | mTLS between collector and ingestion-api. TLS 1.3 minimum on all external endpoints. |
| Encrypted storage | S3 SSE-KMS for raw evidence, Postgres TDE (or disk-level), per-tenant KMS keys. |
| Tenant isolation | `tenant_id` enforced at row level (Postgres RLS) AND at the object store prefix level. No cross-tenant joins possible. |
| Evidence retention | Per-tenant retention policy (default 90 days raw, 2 years normalized). Automated purge job. Legal-hold flag overrides. |
| Secrets redaction | Pre-ingestion redaction pass on collector side (regex + entropy heuristics for tokens/keys) AND post-ingestion in normalizer. Redacted strings replaced with stable hashes so correlation still works. |
| Command allowlist | OPA policy bundle shipped with collector; commands not in allowlist refuse to execute even if injected. |
| Audit logging | Every API call, every agent invocation, every model call, every report access — append-only audit log to separate Postgres table + S3 archive. |
| RBAC | Roles: `viewer`, `engineer`, `auditor`, `admin`, `tenant_admin`, `superadmin`. Enforced at API gateway, also at row level. |
| Self-hosted option | Helm chart of full stack; air-gapped mode disables egress and forces local models; license-key gated. |
| Prompt injection defense | Tool output passed to AI is wrapped in a content envelope; system prompt instructs agents to treat evidence as untrusted data, never as instructions. |

---

## 8. Tool Integration Strategy

Connectors are organized by integration shape, not by domain.

### 8.1 CLI tools (collector-side execution)
Run inside the client environment via collector. Output parsed by per-tool parser modules in `collector/parsers/`.

- Hardware: `lshw`, `dmidecode`, `lscpu`, `lsblk`, `lspci`, `hwloc`, `smartctl`, `nvme-cli`, `nvidia-smi`, `lm-sensors`, `IPMItool`
- Security: `nmap`, `nuclei`, `lynis`, `openscap`, `osquery`, `gitleaks`, `trivy`, `grype`, `syft`, `kube-bench`, `kubescape`
- Performance: `perf`, `bpftrace`, `py-spy`, `async-profiler`, `pprof`, `fio`, `iperf3`, `stress-ng`

### 8.2 APIs
Pulled from the control plane (or from collector for on-prem only systems).

- Cloud: AWS (boto3), GCP, Azure SDKs — Config, IAM, CloudTrail, VPC, S3, EC2, EKS
- Kubernetes: client-go / official Python client; reads RBAC, NetworkPolicies, PodSecurity, images, resource limits
- Observability: Prometheus HTTP API, Grafana API, Loki, Tempo, Jaeger
- SaaS scanners: Nessus, Burp Enterprise, ZAP (REST API)
- Posture: Prowler, ScoutSuite, Checkov (run as containers, JSON output)

### 8.3 Database connectors
Read-only role. Per-engine module.

- PostgreSQL: `pg_stat_statements`, `pg_stat_activity`, replication views, index stats
- MySQL / MariaDB: `performance_schema`, `pt-query-digest` ingestion
- Redis, MongoDB, ClickHouse: stats commands
- Cloud DBs: provider APIs (RDS, Cloud SQL, Cosmos DB)

### 8.4 Hardware telemetry
- Out-of-band: Redfish (preferred), IPMI (fallback)
- In-band: DCGM exporter for GPUs, lm-sensors for thermals
- Storage: SMART via `smartctl`, NVMe via `nvme-cli`
- Firmware inventory: `fwupdmgr get-devices`

### 8.5 Tool execution contract
Every integration ships:
1. Detector — "is this tool installed and what version?"
2. Runner — produces raw bytes + exit code + timing
3. Parser — converts raw to `EvidenceItem.parsed`
4. Schema-version pin — bump on tool upgrade

---

## 9. First MVP Scope

The first version is a single-tenant, internally-operated assessment platform for Linux + AWS + Kubernetes + Postgres environments. No SaaS portal yet (CLI submit + simple web view).

In scope:

- **Collector (Go)** supporting Linux hosts: hardware inventory, Lynis, OpenSCAP, osquery snapshot, perf snapshot, fio, smartctl
- **AWS connector** (Python) reading via `SecurityAudit` role: IAM, S3, EC2, VPC, CloudTrail, Config
- **Kubernetes connector** ingesting `kube-bench` + `kubescape` + native RBAC/PodSecurity reads
- **Vulnerability ingestion** for Trivy (image) and Nessus (host) JSON output
- **Performance ingestion** for Prometheus (scrape a list of metrics) + node_exporter
- **Postgres connector** for `pg_stat_statements` + indexes + replication lag
- **Normalization** for all of the above into the `EvidenceItem` schema
- **Five agents implemented:** Intake, Normalization (mostly deterministic with AI fill-in for ambiguous parses), Security Analysis, Performance Analysis, RiskRank, Report
- **Deterministic risk scoring** with AI-written rationale per finding
- **Blueprint Agent** generating: Linux hardening profile (CIS-derived YAML), AWS baseline (Terraform module), K8s baseline (Helm values diff), Postgres tuning (SQL + postgresql.conf snippet)
- **Reports:** Executive PDF + engineer Markdown/HTML
- **Web view:** read-only Next.js page per run showing findings, blueprints, links to PDF
- **Model gateway:** Anthropic primary, OpenAI fallback, local Llama option (manual switch)
- **Single-tenant Postgres + S3 (or MinIO)**, deployed via Docker Compose for v0 and Helm by v0.5

Explicitly **out of scope** for MVP: drift monitoring, multi-tenant SaaS portal, verification loop (deferred to Phase 3), Cloud/K8s/DB/Hardware agents as separate workers (rolled into Security + Performance agents initially), Windows collector, GPU/Redfish hardware telemetry.

---

## 10. Future Product Modules

| Module | Description | Earliest phase |
|---|---|---|
| **DriftGuard** | Continuous configuration drift detection. Reruns a slimmed collection plan on schedule and diffs against last accepted baseline. | Phase 4 |
| **PerfLens** | Deep performance diagnosis module with flamegraph capture, eBPF-based hotpath analysis, query plan inspection. | Phase 3 |
| **InfraScope** | Hardware/topology mapping: NUMA, GPU interconnects, storage tiers, network fabric. Visualizes via portal. | Phase 3 |
| **ProofPack** | Productized verification engine — captures baseline, drives remediation tracking, produces signed before/after proof report. | Phase 3 |
| **Client-facing SaaS portal** | Multi-tenant, self-service onboarding, billing, scheduled runs. | Phase 4 |
| **Self-hosted enterprise edition** | Helm + Terraform installer, license key, air-gapped support, BYO model. | Phase 4 |
| **Compliance overlays** | Map findings to PCI / HIPAA / SOC2 / ISO27001 controls; generate auditor evidence pack. | Phase 4+ |
| **Marketplace of blueprints** | Curated and community-contributed blueprint modules. | Post-GA |

---

## 11. Recommended Technology Stack

Bias toward boring, well-understood tools.

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI + Pydantic v2 | Best AI ecosystem, async, schema-first |
| Collector | Go 1.22 | Single static binary, minimal runtime in client env, no Python required |
| Frontend | Next.js 14 + TypeScript + shadcn/ui + Tailwind | Boring, fast, easy to hire for |
| Primary DB | PostgreSQL 16 (JSONB for evidence) | Single source of truth, RLS for tenant isolation |
| Search | OpenSearch | Faceted search over findings/assets |
| Queue + workflow | Temporal | Durable workflows, retries, replay — perfect for long agent DAGs |
| Object storage | S3 (cloud) / MinIO (self-host) | Industry standard |
| Cache | Redis | Session, rate limits, light cross-service signalling |
| Model gateway | Python service over LiteLLM + custom routing | Provider abstraction without lock-in |
| Auth | OIDC (Auth0/Okta for SaaS; Keycloak for self-host) | Standard, role-mappable |
| Policy | Open Policy Agent (Rego) | Command allowlists, scope guards |
| Observability | OpenTelemetry → Prometheus + Grafana + Loki + Tempo (dogfooded) | Our own product values are observability ones; eat our cooking |
| Secrets | HashiCorp Vault (self-host) / AWS Secrets Manager (SaaS) | Standard |
| Deployment | Docker for dev, Helm on Kubernetes for prod, Terraform for cloud infra | Standard |
| CI/CD | GitHub Actions | Standard |
| Packaging — collector | Single Go binary + signed tarball + Debian/RPM + container image | Maximum reach |
| Packaging — backend | Container images per service, Helm chart for full stack | Self-host parity |
| Report rendering | WeasyPrint (PDF) + React static export (HTML) | Boring, deterministic |

---

## 12. Build Sequence

### Phase 1 — Foundations (weeks 1–6)
**Goal:** prove the pipeline end-to-end on one Linux host with one tool.

1. Repo monorepo layout, CI, dev compose
2. Postgres schema for `asset`, `evidence_item`, `finding`, `run`
3. S3 buckets + KMS keys
4. `ingestion-api` (FastAPI): bundle upload, signature verify, persist
5. Collector v0 (Go): Linux only, runs `lshw` + `lscpu` + `lsblk` + Lynis, packages tarball, uploads
6. Parser for each MVP tool; produces `EvidenceItem` rows
7. Manual report generator (Jinja → PDF) over the normalized data — no AI yet
8. Audit log table + writer

**Exit:** A run from collector to PDF works without any AI.

### Phase 2 — Agents + Risk + Blueprints (weeks 7–14)
**Goal:** AI value layer.

1. Model gateway service + LiteLLM integration + routing table
2. Temporal install + run workflow skeleton
3. Intake Agent + Collection Planner (light AI, mostly templated)
4. Evidence Normalization Agent (deterministic parsers + AI for ambiguous)
5. Security Analysis Agent + Performance Analysis Agent
6. Risk scoring engine (deterministic) + RiskRank rationale (AI)
7. Blueprint Agent v1: Linux hardening, AWS baseline, K8s baseline, Postgres tuning
8. Report Agent producing executive + engineer reports with AI-written narrative tied to evidence
9. Output schema validation + retry/escalate logic
10. Cost accounting + per-run cost cap

**Exit:** A run produces AI-driven prioritized findings with target-state blueprints, every claim cited.

### Phase 3 — Verification + Portal + Multi-tenant (weeks 15–24)
**Goal:** productize for service delivery.

1. Verification Engine + Verification Agent: pre/post tests, delta reports
2. Client portal (Next.js): runs list, findings, blueprints, report download, evidence drill-down
3. Admin console: tenants, model routing config, agent versions, audit viewer
4. Tenant isolation (Postgres RLS, S3 prefix policy, KMS keys per tenant)
5. RBAC + OIDC
6. Split Cloud, K8s, Database, Hardware into dedicated agents
7. Webhooks: Slack, Jira, ServiceNow
8. PerfLens, InfraScope, ProofPack modules ship under feature flags

**Exit:** Internal services org can run paid engagements through the platform end-to-end.

### Phase 4 — Drift + Packaging (weeks 25–36)
**Goal:** SaaS-able and self-host-able.

1. DriftGuard scheduler + comparison engine
2. Multi-tenant billing + metering
3. SaaS-grade hardening (rate limits, abuse controls, status page)
4. Helm chart + Terraform module for self-host
5. Air-gapped mode (egress denial, local-model-only routing)
6. License key system + offline activation
7. Compliance overlays (PCI/HIPAA/SOC2)

**Exit:** Both deployment modes (SaaS + self-host) are GA.

---

## 13. Key Engineering Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Bad AI recommendations | High | High | Strict output schemas; every finding must cite evidence; Critic Agent on critical findings; human-in-the-loop gate before delivery; expert review queue with feedback loop into prompt eval set |
| Hallucinated findings (made-up CVE, port, file) | Med | Critical | Hard rule: agent outputs rejected if `evidence_ids` empty; cross-check claimed CVE/CWE against authoritative DBs; rendered reports show evidence inline so reviewers can spot-check |
| Unsafe commands executed by collector | Low | Critical | OPA-enforced allowlist signed into collector binary; read-only default; write profile requires separate signed authorization per run; sandbox subprocess (seccomp/AppArmor where available) |
| Tool output schema drift between versions | High | Med | Tool-version pinning per parser; parser test fixtures captured per version; CI runs all parsers against fixture corpus; runtime parser version mismatch flagged on ingest |
| Sensitive data exposure | Med | Critical | Two-stage redaction (collector + normalizer); secret scanner pre-upload; deny-list of high-risk paths; per-tenant KMS; no raw evidence ever sent to model — only normalized fields |
| Poor tenant isolation | Low | Critical | Postgres RLS on every tenant-scoped table; integration test that asserts no cross-tenant read is possible; per-tenant KMS keys; S3 bucket policies enforce prefix isolation |
| Scanner licensing conflicts | Med | Med | Maintain a license-matrix doc; commercial scanners (Nessus, Burp) integrated via API, not redistributed; clearly separate "bring your own license" tools from bundled OSS |
| Scaling large evidence sets | Med | Med | Evidence stored in S3, not Postgres; agents receive references not blobs; normalizer streams large outputs; OpenSearch for query-heavy access; per-run evidence budget |
| Model cost overruns | High | Med | Per-tenant + per-run hard caps; routing favors cheaper tiers by default; prompt caching aggressive; token accounting per agent call; cost dashboard; budget alerts |
| Provider outage | Med | Med | Multi-provider routing with fallback chain; health checks + cooldown on failure; local model option always available |
| Client trust and auditability | High | Critical | Every finding cites evidence; every agent run logged with model + prompt hash; reports include "how this was produced" appendix; evidence bundles retained per retention policy; SOC2-aimed control set from day one |
| Prompt injection via tool output | Med | High | Tool output wrapped in untrusted-content envelope; system prompts instruct treat-as-data; never execute strings from model output without policy check |

---

## Repository Layout (proposed)

```
auditor/
├── ARCHITECTURE.md              # this document
├── README.md
├── docs/                        # ADRs, schemas, runbooks
├── schemas/                     # canonical JSON Schemas (generated from Pydantic)
├── proto/                       # gRPC for collector ↔ ingestion (optional)
├── collector/                   # Go
│   ├── cmd/auditor-collect/
│   ├── internal/runner/
│   ├── internal/parsers/
│   ├── internal/policy/         # OPA allowlist embedded
│   └── pkg/bundle/
├── services/
│   ├── ingestion-api/           # FastAPI
│   ├── normalizer-worker/       # Python
│   ├── orchestrator/            # Temporal workflows + activities
│   ├── model-gateway/           # Python
│   ├── scoring-engine/
│   ├── blueprint-generator/
│   ├── verification-engine/
│   └── report-generator/
├── agents/                      # agent definitions (YAML + prompts + output schemas)
│   ├── intake/
│   ├── collection_planner/
│   ├── normalization/
│   ├── security_analysis/
│   ├── performance_analysis/
│   ├── cloud_optimization/
│   ├── kubernetes/
│   ├── database/
│   ├── hardware/
│   ├── riskrank/
│   ├── blueprint/
│   ├── verification/
│   └── report/
├── blueprints/                  # target-state templates (terraform/, helm/, sql/, yaml/)
├── connectors/                  # cloud/k8s/db/observability connectors
├── frontend/                    # Next.js portal + admin console
├── deploy/
│   ├── docker-compose/
│   ├── helm/
│   └── terraform/
├── packages/                    # shared Python models, Go shared libs
└── tests/                       # integration + golden-file fixtures
```

---

## Open Questions (to resolve before Phase 2 implementation)

1. Workflow engine: confirm Temporal vs. simpler Celery+beat — Temporal is preferred but adds infra; revisit at end of Phase 1.
2. Model gateway: build on LiteLLM or write thin native abstraction? LiteLLM recommended for v1, revisit if it constrains us.
3. Collector packaging: ship as one binary supporting all tools via subcommands, or as a thin shell with downloadable tool modules? One-binary-with-subcommands preferred.
4. Whether the Normalization Agent is AI-first or deterministic-first with AI fallback — currently planned as deterministic-first.
5. Whether to support a "no-agent" mode (rules-only) for the most-conservative clients — likely yes, gated by tenant config.
