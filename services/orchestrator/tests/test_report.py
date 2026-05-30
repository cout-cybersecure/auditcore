"""Report-assembly tests. The integrity rule: a section may only reference
observations that exist for the run; unknown refs are stripped/flagged."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from auditcore_agents import AgentRegistry
from auditcore_orchestrator.report import build_report_input
from auditcore_orchestrator.runner import assemble_run_report

from .conftest import FakeGateway, FakeRepo, make_asset, make_observation

AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"


@pytest.mark.asyncio
async def test_valid_sections_are_written_and_refs_validated():
    registry = AgentRegistry.load(AGENTS_DIR)
    asset = make_asset()
    obs = make_observation(asset.id)
    foreign = str(uuid4())

    payload = {"sections": [
        {"audience": "technical", "order": 0, "title": "Hardware",
         "body_md": f"The host has 16 CPUs [[observation:{obs.id}]].",
         "embedded_observations": [str(obs.id), foreign]},
        {"audience": "summary", "order": 0, "title": "Overview",
         "body_md": "A single-socket Linux host.",
         "embedded_observations": []},
    ]}
    repo = FakeRepo(observations=[obs])
    gw = FakeGateway(payload)

    result = await assemble_run_report(
        run_id=uuid4(), repo=repo, registry=registry, gateway=gw,
        tenant_id="00000000-0000-0000-0000-000000000001",
    )

    assert result.sections_written == 2
    # The foreign ref was stripped from embedded_observations and flagged.
    tech = next(s for s in repo.sections if s.audience == "technical")
    assert tech.embedded_observations == [obs.id]
    assert foreign in result.unknown_refs
    # status went to complete
    assert "complete" in repo.statuses
    assert gw.calls[0]["task_kind"] == "LONG_CONTEXT"


@pytest.mark.asyncio
async def test_inline_marker_to_unknown_observation_is_flagged():
    registry = AgentRegistry.load(AGENTS_DIR)
    asset = make_asset()
    obs = make_observation(asset.id)
    unknown = str(uuid4())
    payload = {"sections": [
        {"audience": "technical", "order": 0, "title": "X",
         "body_md": f"Mentions [[observation:{unknown}]] which does not exist.",
         "embedded_observations": []},
    ]}
    repo = FakeRepo(observations=[obs])
    result = await assemble_run_report(
        run_id=uuid4(), repo=repo, registry=registry, gateway=FakeGateway(payload),
        tenant_id="t",
    )
    assert unknown in result.unknown_refs


@pytest.mark.asyncio
async def test_no_observations_short_circuits():
    registry = AgentRegistry.load(AGENTS_DIR)
    repo = FakeRepo(observations=[])
    result = await assemble_run_report(
        run_id=uuid4(), repo=repo, registry=registry, gateway=FakeGateway({}),
        tenant_id="t",
    )
    assert result.sections_written == 0
    assert any("no observations" in d for d in result.dropped)


@pytest.mark.asyncio
async def test_invalid_audience_section_dropped():
    registry = AgentRegistry.load(AGENTS_DIR)
    asset = make_asset()
    obs = make_observation(asset.id)
    payload = {"sections": [
        {"audience": "executive", "order": 0, "title": "X",
         "body_md": "y", "embedded_observations": []},
    ]}
    repo = FakeRepo(observations=[obs])
    result = await assemble_run_report(
        run_id=uuid4(), repo=repo, registry=registry, gateway=FakeGateway(payload),
        tenant_id="t",
    )
    assert result.sections_written == 0
    assert any("invalid audience" in d for d in result.dropped)


def test_report_input_includes_observation_ids():
    asset = make_asset()
    obs = make_observation(asset.id)
    content = build_report_input([obs])
    assert str(obs.id) in content
    assert "observation" in content.lower()
