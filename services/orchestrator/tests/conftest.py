from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from auditcore_orchestrator.gateway_client import GatewayResult
from auditcore_orchestrator.repo import AssetRow, EvidenceRow, ObservationWrite


class FakeGateway:
    """Returns a pre-seeded parsed payload; records the call."""

    def __init__(self, payload: dict[str, Any] | None,
                 schema_valid: bool = True, errors: list[str] | None = None) -> None:
        self.payload = payload
        self.schema_valid = schema_valid
        self.errors = errors or []
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> GatewayResult:
        self.calls.append(kwargs)
        return GatewayResult(
            parsed=self.payload,
            schema_valid=self.schema_valid,
            schema_errors=self.errors,
            model="fake-model",
            provider="fake",
            cost_usd=0.01,
            content="",
        )


@dataclass
class FakeRepo:
    evidence: dict[str, list[EvidenceRow]] = field(default_factory=dict)
    assets: list[AssetRow] = field(default_factory=list)
    written: list[ObservationWrite] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    audits: list[tuple[str, dict]] = field(default_factory=list)

    def categories_present(self, run_id: UUID) -> list[str]:
        return sorted(self.evidence)

    def evidence_for_category(self, run_id: UUID, category: str) -> list[EvidenceRow]:
        return self.evidence.get(category, [])

    def assets_for_run(self, run_id: UUID) -> list[AssetRow]:
        return self.assets

    def write_observations(self, obs: list[ObservationWrite]) -> int:
        self.written.extend(obs)
        return len(obs)

    def set_run_status(self, run_id: UUID, status: str) -> None:
        self.statuses.append(status)

    def audit(self, run_id: UUID, action: str, metadata: dict) -> None:
        self.audits.append((action, metadata))


def make_asset() -> AssetRow:
    return AssetRow(uuid4(), "host", "host:abc", "host-a", {"cpu_model": "Xeon"})


def make_evidence(asset_id: UUID, category: str = "hardware") -> EvidenceRow:
    return EvidenceRow(uuid4(), asset_id, "lscpu", category, {"CPU(s)": 16})
