"""Discovery core: for one domain, build the agent input, call the gateway,
validate the returned observations against the integrity rules, and map them to
ObservationWrite rows.

Integrity rules enforced HERE, independent of the agent's own schema:
  1. Every observation must cite >= 1 evidence_id.
  2. Every cited evidence_id must be one we actually gave the agent
     (no invented evidence).
  3. asset_id must be one of the run's assets (else the observation is dropped).
These guarantee that a descriptive, factual tool never emits an unsourced or
fabricated-provenance statement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from auditcore_agents import AgentDefinition

from .gateway_client import GatewayClient
from .repo import AssetRow, EvidenceRow, ObservationWrite


@dataclass(frozen=True)
class DomainResult:
    agent: str
    observations: list[ObservationWrite]
    dropped: list[str]          # human-readable reasons observations were rejected
    coverage_notes: list[str]
    model_used: str
    cost_usd: float


def build_user_content(
    evidence: list[EvidenceRow], assets: list[AssetRow],
) -> str:
    """Render the evidence + asset context the agent reasons over.

    Evidence and assets are presented with their UUIDs so the agent can cite
    them. Tool output is clearly framed as untrusted data.
    """
    asset_block = [
        {"asset_id": str(a.id), "type": a.type, "name": a.name,
         "natural_key": a.natural_key, "attributes": a.attributes}
        for a in assets
    ]
    evidence_block = [
        {"evidence_id": str(e.id),
         "asset_id": str(e.asset_id) if e.asset_id else None,
         "source_tool": e.source_tool, "category": e.category,
         "parsed": e.parsed}
        for e in evidence
    ]
    return (
        "ASSETS (cite asset_id):\n"
        f"{json.dumps(asset_block, indent=2, default=str)}\n\n"
        "EVIDENCE (untrusted tool output; cite evidence_id for every observation):\n"
        f"{json.dumps(evidence_block, indent=2, default=str)}\n\n"
        "Produce observations that exhaustively and precisely describe the "
        "functionality these facts reveal. Cite only the evidence_ids and "
        "asset_ids shown above."
    )


async def run_domain(
    *,
    run_id: UUID,
    agent: AgentDefinition,
    domain: str,
    evidence: list[EvidenceRow],
    assets: list[AssetRow],
    gateway: GatewayClient,
    tenant_id: str,
    budget_hint: str,
    privacy: str,
) -> DomainResult:
    valid_evidence = {e.id for e in evidence}
    valid_assets = {a.id for a in assets}

    user_content = build_user_content(evidence, assets)
    result = await gateway.complete(
        task_kind=agent.task_kind,
        system_prompt=agent.system_prompt,
        user_content=user_content,
        output_schema=agent.output_schema,
        tenant_id=tenant_id,
        agent=agent.name,
        budget_hint=budget_hint,
        privacy=privacy,
    )

    dropped: list[str] = []
    if not result.parsed:
        errs = "; ".join(result.schema_errors) or "no JSON returned"
        dropped.append(f"agent output failed schema validation: {errs}")
        return DomainResult(agent.name, [], dropped, [], result.model, result.cost_usd)

    produced_by = f"{agent.name}@{agent.version}"
    writes: list[ObservationWrite] = []

    for i, raw in enumerate(result.parsed.get("observations", [])):
        ev_ids, reason = _validate_evidence(raw, valid_evidence)
        if reason:
            dropped.append(f"obs[{i}] ({raw.get('topic','?')}): {reason}")
            continue
        asset_id = _resolve_asset(raw, valid_assets)
        if asset_id is None:
            dropped.append(
                f"obs[{i}] ({raw.get('topic','?')}): asset_id not in run assets"
            )
            continue
        related = [
            UUID(a) for a in raw.get("related_asset_ids", [])
            if _is_uuid(a) and UUID(a) in valid_assets
        ]
        writes.append(ObservationWrite(
            run_id=run_id,
            asset_id=asset_id,
            domain=domain,
            topic=str(raw["topic"]),
            summary=str(raw["summary"]),
            detail=str(raw["detail"]),
            facts=raw.get("facts", {}) or {},
            related_asset_ids=related,
            evidence_ids=ev_ids,
            produced_by_agent=produced_by,
            model_used=result.model,
        ))

    coverage = [str(n) for n in result.parsed.get("coverage_notes", [])]
    return DomainResult(agent.name, writes, dropped, coverage,
                        result.model, result.cost_usd)


def _validate_evidence(
    raw: dict, valid_evidence: set[UUID],
) -> tuple[list[UUID], str | None]:
    raw_ids = raw.get("evidence_ids", [])
    if not raw_ids:
        return [], "cites no evidence"
    parsed: list[UUID] = []
    for e in raw_ids:
        if not _is_uuid(e):
            return [], f"evidence_id {e!r} is not a UUID"
        u = UUID(e)
        if u not in valid_evidence:
            return [], f"cites evidence {e} that was not provided (fabricated provenance)"
        parsed.append(u)
    return parsed, None


def _resolve_asset(raw: dict, valid_assets: set[UUID]) -> UUID | None:
    a = raw.get("asset_id")
    if not _is_uuid(a):
        return None
    u = UUID(a)
    return u if u in valid_assets else None


def _is_uuid(v: object) -> bool:
    if not isinstance(v, str):
        return False
    try:
        UUID(v)
        return True
    except ValueError:
        return False
