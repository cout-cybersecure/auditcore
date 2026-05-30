"""Drives a full discovery pass for a run: for every domain that has normalized
evidence, run its discovery agent and persist the resulting observations."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from auditcore_agents import AgentRegistry

from . import domains
from .discovery import run_domain
from .gateway_client import GatewayClient
from .repo import Repo

log = logging.getLogger("auditcore.orchestrator")


@dataclass
class RunReport:
    run_id: UUID
    observations_written: int = 0
    dropped: list[str] = field(default_factory=list)
    coverage_notes: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    domains_run: list[str] = field(default_factory=list)


async def discover_run(
    *,
    run_id: UUID,
    repo: Repo,
    registry: AgentRegistry,
    gateway: GatewayClient,
    tenant_id: str,
    budget_hint: str = "normal",
    privacy: str = "standard",
) -> RunReport:
    repo.set_run_status(run_id, "discovering")
    report = RunReport(run_id=run_id)

    categories = repo.categories_present(run_id)
    assets = repo.assets_for_run(run_id)

    # Group categories by the agent that handles them, so each agent runs once
    # over the union of its categories' evidence.
    by_agent: dict[str, tuple[str, list[str]]] = {}
    for category in categories:
        binding = domains.binding_for(category)
        if binding is None:
            report.dropped.append(f"no discovery agent for category {category!r}")
            continue
        domain, cats = by_agent.setdefault(binding.agent, (binding.domain, []))
        cats.append(category)

    for agent_name, (domain, cats) in by_agent.items():
        if agent_name not in registry:
            report.dropped.append(f"agent {agent_name!r} not in registry")
            continue
        agent = registry.get(agent_name)

        evidence = [
            e for cat in cats for e in repo.evidence_for_category(run_id, cat)
        ]
        if not evidence:
            continue

        log.info("running discovery agent %s over %d evidence items",
                 agent_name, len(evidence))
        result = await run_domain(
            run_id=run_id, agent=agent, domain=domain,
            evidence=evidence, assets=assets, gateway=gateway,
            tenant_id=tenant_id, budget_hint=budget_hint, privacy=privacy,
        )

        written = repo.write_observations(result.observations)
        report.observations_written += written
        report.dropped.extend(result.dropped)
        report.coverage_notes.extend(result.coverage_notes)
        report.cost_usd += result.cost_usd
        report.domains_run.append(agent_name)

        repo.audit(run_id, "discovery.agent_run", {
            "agent": agent_name, "domain": domain,
            "evidence": len(evidence), "written": written,
            "dropped": len(result.dropped), "model": result.model_used,
            "cost_usd": result.cost_usd,
        })

    repo.set_run_status(run_id, "reporting")
    repo.audit(run_id, "discovery.complete", {
        "observations": report.observations_written,
        "dropped": len(report.dropped),
        "cost_usd": report.cost_usd,
    })
    return report
