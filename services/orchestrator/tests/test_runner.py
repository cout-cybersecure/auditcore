from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from auditcore_agents import AgentRegistry
from auditcore_orchestrator.runner import discover_run

from .conftest import FakeGateway, FakeRepo, make_asset, make_evidence

AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"


@pytest.mark.asyncio
async def test_full_run_writes_observations_and_sets_status():
    registry = AgentRegistry.load(AGENTS_DIR)
    asset = make_asset()
    ev = make_evidence(asset.id, category="hardware")
    repo = FakeRepo(evidence={"hardware": [ev]}, assets=[asset])

    payload = {"observations": [{
        "asset_id": str(asset.id),
        "topic": "CPU topology",
        "summary": "16 logical CPUs",
        "detail": "Single socket, 8 cores, 2 threads/core.",
        "facts": {"cpus": 16},
        "evidence_ids": [str(ev.id)],
    }]}
    gw = FakeGateway(payload)

    report = await discover_run(
        run_id=uuid4(), repo=repo, registry=registry, gateway=gw,
        tenant_id="00000000-0000-0000-0000-000000000001",
    )

    assert report.observations_written == 1
    assert "hardware" in report.domains_run
    assert len(repo.written) == 1
    assert repo.written[0].domain == "hardware"
    # status transitions: discovering then reporting
    assert repo.statuses == ["discovering", "reporting"]
    # the hardware agent ran with the REASON task kind from its yaml
    assert gw.calls[0]["task_kind"] == "REASON"


@pytest.mark.asyncio
async def test_unknown_category_is_reported_not_fatal():
    registry = AgentRegistry.load(AGENTS_DIR)
    asset = make_asset()
    ev = make_evidence(asset.id, category="quantum_widgets")
    repo = FakeRepo(evidence={"quantum_widgets": [ev]}, assets=[asset])

    report = await discover_run(
        run_id=uuid4(), repo=repo, registry=registry, gateway=FakeGateway({}),
        tenant_id="t",
    )

    assert report.observations_written == 0
    assert any("no discovery agent" in d for d in report.dropped)
    assert repo.statuses == ["discovering", "reporting"]
