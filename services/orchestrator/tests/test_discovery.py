"""Discovery-core tests. The integrity guard is the most important behavior:
the orchestrator must reject observations that cite no evidence or fabricate
evidence/asset provenance, even if the agent's own schema passed."""
from __future__ import annotations

from uuid import uuid4

import pytest
from auditcore_agents import AgentDefinition
from auditcore_orchestrator.discovery import build_user_content, run_domain
from pathlib import Path

from .conftest import FakeGateway, make_asset, make_evidence


def _agent() -> AgentDefinition:
    return AgentDefinition(
        name="hardware", version="0.2.0", purpose="discover hardware",
        task_kind="REASON", budget_hint="normal", privacy="standard",
        system_prompt="describe hardware facts", output_schema=None,
        contract=(), directory=Path("."),
    )


@pytest.mark.asyncio
async def test_valid_observation_is_written():
    asset = make_asset()
    ev = make_evidence(asset.id)
    payload = {"observations": [{
        "asset_id": str(asset.id),
        "topic": "CPU topology",
        "summary": "16 logical CPUs",
        "detail": "Single socket, 8 cores, 2 threads/core.",
        "facts": {"cpus": 16},
        "evidence_ids": [str(ev.id)],
    }], "coverage_notes": ["no GPU evidence"]}
    gw = FakeGateway(payload)

    result = await run_domain(
        run_id=uuid4(), agent=_agent(), domain="hardware",
        evidence=[ev], assets=[asset], gateway=gw,
        tenant_id="t", budget_hint="normal", privacy="standard",
    )

    assert len(result.observations) == 1
    o = result.observations[0]
    assert o.topic == "CPU topology"
    assert o.evidence_ids == [ev.id]
    assert o.produced_by_agent == "hardware@0.2.0"
    assert o.model_used == "fake-model"
    assert result.coverage_notes == ["no GPU evidence"]
    assert not result.dropped


@pytest.mark.asyncio
async def test_observation_without_evidence_is_dropped():
    asset = make_asset()
    ev = make_evidence(asset.id)
    payload = {"observations": [{
        "asset_id": str(asset.id), "topic": "X", "summary": "y", "detail": "z",
        "evidence_ids": [],
    }]}
    result = await run_domain(
        run_id=uuid4(), agent=_agent(), domain="hardware",
        evidence=[ev], assets=[asset], gateway=FakeGateway(payload),
        tenant_id="t", budget_hint="normal", privacy="standard",
    )
    assert result.observations == []
    assert any("cites no evidence" in d for d in result.dropped)


@pytest.mark.asyncio
async def test_fabricated_evidence_is_rejected():
    asset = make_asset()
    ev = make_evidence(asset.id)
    fake_evidence_id = str(uuid4())  # not in the provided set
    payload = {"observations": [{
        "asset_id": str(asset.id), "topic": "X", "summary": "y", "detail": "z",
        "evidence_ids": [fake_evidence_id],
    }]}
    result = await run_domain(
        run_id=uuid4(), agent=_agent(), domain="hardware",
        evidence=[ev], assets=[asset], gateway=FakeGateway(payload),
        tenant_id="t", budget_hint="normal", privacy="standard",
    )
    assert result.observations == []
    assert any("fabricated provenance" in d for d in result.dropped)


@pytest.mark.asyncio
async def test_observation_with_foreign_asset_is_dropped():
    asset = make_asset()
    ev = make_evidence(asset.id)
    payload = {"observations": [{
        "asset_id": str(uuid4()),  # not a run asset
        "topic": "X", "summary": "y", "detail": "z",
        "evidence_ids": [str(ev.id)],
    }]}
    result = await run_domain(
        run_id=uuid4(), agent=_agent(), domain="hardware",
        evidence=[ev], assets=[asset], gateway=FakeGateway(payload),
        tenant_id="t", budget_hint="normal", privacy="standard",
    )
    assert result.observations == []
    assert any("asset_id not in run assets" in d for d in result.dropped)


@pytest.mark.asyncio
async def test_schema_failure_returns_no_observations():
    asset = make_asset()
    ev = make_evidence(asset.id)
    gw = FakeGateway(payload=None, schema_valid=False, errors=["root: missing 'observations'"])
    result = await run_domain(
        run_id=uuid4(), agent=_agent(), domain="hardware",
        evidence=[ev], assets=[asset], gateway=gw,
        tenant_id="t", budget_hint="normal", privacy="standard",
    )
    assert result.observations == []
    assert any("schema validation" in d for d in result.dropped)


def test_user_content_frames_evidence_as_untrusted():
    asset = make_asset()
    ev = make_evidence(asset.id)
    content = build_user_content([ev], [asset])
    assert "untrusted" in content.lower()
    assert str(ev.id) in content
    assert str(asset.id) in content
