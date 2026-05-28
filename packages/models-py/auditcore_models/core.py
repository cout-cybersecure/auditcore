from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Domain(str, Enum):
    SECURITY = "security"
    PERFORMANCE = "performance"
    CLOUD = "cloud"
    K8S = "k8s"
    DB = "db"
    HARDWARE = "hardware"


class AssetType(str, Enum):
    HOST = "host"
    VM = "vm"
    CONTAINER = "container"
    POD = "pod"
    K8S_NODE = "k8s_node"
    K8S_CLUSTER = "k8s_cluster"
    CLOUD_ACCOUNT = "cloud_account"
    CLOUD_RESOURCE = "cloud_resource"
    DATABASE = "database"
    GPU = "gpu"
    NETWORK_DEVICE = "network_device"
    LOAD_BALANCER = "load_balancer"
    STORAGE_BUCKET = "storage_bucket"


class RunStatus(str, Enum):
    PLANNING = "planning"
    COLLECTING = "collecting"
    NORMALIZING = "normalizing"
    ANALYZING = "analyzing"
    SCORING = "scoring"
    BLUEPRINTING = "blueprinting"
    REPORTING = "reporting"
    COMPLETE = "complete"
    FAILED = "failed"


class Run(BaseModel):
    id: UUID
    tenant_id: UUID
    parent_run_id: UUID | None = None
    scope: dict[str, Any]
    collection_plan: dict[str, Any] | None = None
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    cost_cents: int = 0


class Asset(BaseModel):
    id: UUID
    tenant_id: UUID
    run_id: UUID
    type: AssetType
    natural_key: str
    name: str
    environment: Literal["prod", "staging", "dev", "unknown"] = "unknown"
    importance: int = Field(default=3, ge=1, le=5)
    attributes: dict[str, Any] = Field(default_factory=dict)
    parent_asset_id: UUID | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    first_seen: datetime
    last_seen: datetime


class EvidenceItem(BaseModel):
    id: UUID
    tenant_id: UUID
    run_id: UUID
    asset_id: UUID | None = None
    source_tool: str
    source_tool_version: str
    collected_at: datetime
    category: Literal[
        "security", "performance", "cloud", "kubernetes",
        "database", "hardware", "inventory",
    ]
    raw_ref: str  # S3 URI to original output
    parsed: dict[str, Any]
    severity_hint: Severity | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    redactions: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: UUID
    tenant_id: UUID
    run_id: UUID
    asset_id: UUID
    domain: Domain
    title: str
    description: str
    severity: Severity
    cwe: list[str] = Field(default_factory=list)
    cve: list[str] = Field(default_factory=list)
    cis_controls: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID]
    produced_by_agent: str
    model_used: str
    status: Literal[
        "open", "accepted_risk", "fixed", "false_positive", "in_conflict",
    ] = "open"
    created_at: datetime

    @field_validator("evidence_ids")
    @classmethod
    def must_cite_evidence(cls, v: list[UUID]) -> list[UUID]:
        # Hard hallucination guard: a finding without evidence is never valid.
        if not v:
            raise ValueError("Finding must cite at least one evidence_id")
        return v


class RiskScore(BaseModel):
    finding_id: UUID
    exposure: int = Field(ge=0, le=10)
    exploitability: int = Field(ge=0, le=10)
    asset_importance: int = Field(ge=1, le=5)
    blast_radius: int = Field(ge=0, le=10)
    business_impact: int = Field(ge=0, le=10)
    fix_difficulty: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    composite: float = Field(ge=0.0, le=100.0)
    rank: int = Field(ge=1)
    rationale: str
    scored_by_agent: str


class Recommendation(BaseModel):
    id: UUID
    finding_id: UUID
    summary: str
    steps: list[str]
    automation_available: bool = False
    automation_ref: str | None = None
    effort_estimate: Literal["minutes", "hours", "days", "weeks"]
    blast_radius: Literal["isolated", "service", "tenant", "global"]
    requires_change_window: bool = False
    rollback_plan: str


class BlueprintItem(BaseModel):
    id: UUID
    run_id: UUID
    domain: Domain
    target: str
    format: Literal[
        "terraform", "helm", "kustomize", "ansible", "sql", "markdown", "yaml",
    ]
    artifact_ref: str
    sources: list[UUID]
    applies_to_assets: list[UUID]
    idempotent: bool = True
    review_required: bool = True


class VerificationTest(BaseModel):
    id: UUID
    finding_id: UUID
    name: str
    kind: Literal["command", "scan", "metric_check", "query"]
    spec: dict[str, Any]
    baseline_result: dict[str, Any] | None = None
    post_result: dict[str, Any] | None = None
    passed: bool | None = None
    delta_summary: str | None = None


class ReportSection(BaseModel):
    id: UUID
    run_id: UUID
    audience: Literal["executive", "engineer"]
    order: int
    title: str
    body_md: str
    embedded_findings: list[UUID] = Field(default_factory=list)
    embedded_blueprints: list[UUID] = Field(default_factory=list)
