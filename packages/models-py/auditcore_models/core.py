from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class Domain(str, Enum):
    """Discovery domains. These name *what kind of system functionality* an
    observation describes — not a risk category."""
    SECURITY = "security"
    PERFORMANCE = "performance"
    CLOUD = "cloud"
    K8S = "k8s"
    DB = "db"
    HARDWARE = "hardware"
    NETWORK = "network"
    SOFTWARE = "software"


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
    DISCOVERING = "discovering"   # discovery agents are extracting facts
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
    run_id: UUID                       # first run that discovered it
    type: AssetType
    natural_key: str                   # provider+region+resource_id or hostname+uuid
    name: str
    environment: Literal["prod", "staging", "dev", "unknown"] = "unknown"
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
    source_tool: str                   # "lscpu", "hwprobe", "nmap", ...
    source_tool_version: str
    collected_at: datetime
    category: Literal[
        "security", "performance", "cloud", "kubernetes",
        "database", "hardware", "network", "software", "inventory",
    ]
    raw_ref: str                       # object-store URI to the original output
    parsed: dict[str, Any]             # normalized fields per tool parser
    confidence: float = Field(ge=0.0, le=1.0)  # parser confidence in the extraction
    redactions: list[str] = Field(default_factory=list)


class Observation(BaseModel):
    """A precise, factual statement about discovered system functionality.

    Observations are descriptive, not evaluative: they record *what exists and
    how it works*, in exhaustive detail, every claim backed by evidence. There
    is deliberately no severity, score, or recommendation — AuditCore reports
    facts, it does not judge or prescribe.
    """
    id: UUID
    tenant_id: UUID
    run_id: UUID
    asset_id: UUID
    domain: Domain
    topic: str                         # short label, e.g. "SSH authentication", "NUMA layout"
    summary: str                       # one-line factual statement
    detail: str                        # exhaustive, precise description of the functionality
    facts: dict[str, Any] = Field(default_factory=dict)  # structured extracted key/values
    related_asset_ids: list[UUID] = Field(default_factory=list)  # functional relationships
    evidence_ids: list[UUID]           # MUST be non-empty
    produced_by_agent: str             # agent name + version
    model_used: str
    created_at: datetime

    @field_validator("evidence_ids")
    @classmethod
    def must_cite_evidence(cls, v: list[UUID]) -> list[UUID]:
        # A factual observation with no evidence is never valid. This is the
        # core integrity guarantee of a discovery-and-description tool.
        if not v:
            raise ValueError("Observation must cite at least one evidence_id")
        return v


class ReportSection(BaseModel):
    id: UUID
    run_id: UUID
    audience: Literal["technical", "summary"]
    order: int
    title: str
    body_md: str                       # markdown; observation refs as [[observation:UUID]]
    embedded_observations: list[UUID] = Field(default_factory=list)
