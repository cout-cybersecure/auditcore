from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import click
from auditcore_agents import AgentRegistry

from .config import settings
from .gateway_client import HttpGatewayClient
from .repo import PgRepo
from .runner import assemble_run_report, discover_run

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@click.group()
def main() -> None:
    """AuditCore discovery orchestrator."""


@main.command()
@click.argument("run_id")
@click.option("--budget", default=None, help="override budget_hint")
@click.option("--privacy", default=None, help="override privacy tier")
def run(run_id: str, budget: str | None, privacy: str | None) -> None:
    """Run a discovery pass over a normalized run and write observations."""
    registry = AgentRegistry.load(settings.agents_dir)
    repo = PgRepo(settings.db_dsn, UUID(settings.default_tenant_id))
    gateway = HttpGatewayClient(settings.gateway_url)

    report = asyncio.run(discover_run(
        run_id=UUID(run_id),
        repo=repo,
        registry=registry,
        gateway=gateway,
        tenant_id=settings.default_tenant_id,
        budget_hint=budget or settings.budget_hint,
        privacy=privacy or settings.privacy,
    ))

    click.echo(f"run {report.run_id}")
    click.echo(f"  agents run:    {', '.join(report.domains_run) or '(none)'}")
    click.echo(f"  observations:  {report.observations_written}")
    click.echo(f"  dropped:       {len(report.dropped)}")
    for d in report.dropped:
        click.echo(f"    - {d}")
    click.echo(f"  cost (USD):    {report.cost_usd:.4f}")


@main.command()
@click.argument("run_id")
@click.option("--budget", default=None, help="override budget_hint")
@click.option("--privacy", default=None, help="override privacy tier")
def report(run_id: str, budget: str | None, privacy: str | None) -> None:
    """Run the report agent over a run's observations and persist sections."""
    registry = AgentRegistry.load(settings.agents_dir)
    repo = PgRepo(settings.db_dsn, UUID(settings.default_tenant_id))
    gateway = HttpGatewayClient(settings.gateway_url)

    result = asyncio.run(assemble_run_report(
        run_id=UUID(run_id),
        repo=repo,
        registry=registry,
        gateway=gateway,
        tenant_id=settings.default_tenant_id,
        budget_hint=budget or settings.budget_hint,
        privacy=privacy or settings.privacy,
    ))

    click.echo(f"run {result.run_id}")
    click.echo(f"  sections:     {result.sections_written}")
    click.echo(f"  unknown refs: {len(result.unknown_refs)}")
    click.echo(f"  dropped:      {len(result.dropped)}")
    for d in result.dropped:
        click.echo(f"    - {d}")
    click.echo(f"  cost (USD):   {result.cost_usd:.4f}")


if __name__ == "__main__":  # pragma: no cover
    main()
