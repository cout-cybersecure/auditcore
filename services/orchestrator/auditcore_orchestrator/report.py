"""Report assembly: run the report agent over a run's observations and persist
the resulting descriptive sections.

Integrity rule (symmetric with discovery): a section may only reference
observations that actually exist for the run. Any `embedded_observations` id
that is not a real observation is stripped, and any `[[observation:UUID]]`
marker in the body that points at an unknown id is reported. A descriptive
document never cites a fact that was not discovered.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from uuid import UUID

from auditcore_agents import AgentDefinition

from .gateway_client import GatewayClient
from .repo import ObservationRow, ReportSectionWrite

_OBS_REF = re.compile(r"\[\[observation:([0-9a-fA-F-]{36})\]\]")


@dataclass
class ReportResult:
    sections: list[ReportSectionWrite]
    dropped: list[str] = field(default_factory=list)
    unknown_refs: list[str] = field(default_factory=list)
    model_used: str = ""
    cost_usd: float = 0.0


def build_report_input(observations: list[ObservationRow]) -> str:
    obs_block = [
        {"observation_id": str(o.id), "asset_id": str(o.asset_id),
         "domain": o.domain, "topic": o.topic, "summary": o.summary,
         "detail": o.detail, "facts": o.facts}
        for o in observations
    ]
    return (
        "OBSERVATIONS (the discovered facts; reference any with "
        "[[observation:<id>]] and list ids in embedded_observations):\n"
        f"{json.dumps(obs_block, indent=2, default=str)}\n\n"
        "Assemble these into a precise, exhaustive description of the system. "
        "State only what the observations contain."
    )


async def assemble_report(
    *,
    run_id: UUID,
    agent: AgentDefinition,
    observations: list[ObservationRow],
    gateway: GatewayClient,
    tenant_id: str,
    budget_hint: str = "normal",
    privacy: str = "standard",
) -> ReportResult:
    valid_obs = {o.id for o in observations}

    result = await gateway.complete(
        task_kind=agent.task_kind,
        system_prompt=agent.system_prompt,
        user_content=build_report_input(observations),
        output_schema=agent.output_schema,
        tenant_id=tenant_id,
        agent=agent.name,
        budget_hint=budget_hint,
        privacy=privacy,
    )

    out = ReportResult(sections=[], model_used=result.model, cost_usd=result.cost_usd)
    if not result.parsed:
        errs = "; ".join(result.schema_errors) or "no JSON returned"
        out.dropped.append(f"report agent output failed schema validation: {errs}")
        return out

    produced_by = f"{agent.name}@{agent.version}"
    for i, raw in enumerate(result.parsed.get("sections", [])):
        audience = raw.get("audience")
        if audience not in ("technical", "summary"):
            out.dropped.append(f"section[{i}]: invalid audience {audience!r}")
            continue

        body = str(raw.get("body_md", ""))

        # Validate explicit embedded_observations against real observations.
        embedded: list[UUID] = []
        for ref in raw.get("embedded_observations", []):
            if _is_uuid(ref) and UUID(ref) in valid_obs:
                embedded.append(UUID(ref))
            else:
                out.unknown_refs.append(str(ref))

        # Flag inline [[observation:UUID]] markers that point at unknown ids.
        for m in _OBS_REF.findall(body):
            if not _is_uuid(m) or UUID(m) not in valid_obs:
                out.unknown_refs.append(m)

        out.sections.append(ReportSectionWrite(
            run_id=run_id,
            audience=audience,
            order=int(raw.get("order", i)),
            title=str(raw.get("title", "")),
            body_md=body,
            embedded_observations=embedded,
            produced_by_agent=produced_by,
            model_used=result.model,
        ))

    return out


def _is_uuid(v: object) -> bool:
    if not isinstance(v, str):
        return False
    try:
        UUID(v)
        return True
    except ValueError:
        return False
