from pathlib import Path

import pytest

from auditcore_agents import AgentRegistry, AgentSpecError

AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"

EXPECTED_AGENTS = {
    "intake", "collection_planner", "normalization",
    "security_analysis", "performance_analysis", "cloud_analysis",
    "kubernetes", "database", "hardware",
    "report",
}


@pytest.fixture(scope="module")
def registry() -> AgentRegistry:
    return AgentRegistry.load(AGENTS_DIR)


def test_all_ten_agents_load(registry: AgentRegistry) -> None:
    assert set(registry.names()) == EXPECTED_AGENTS
    assert len(registry) == 10


def test_every_agent_has_a_system_prompt(registry: AgentRegistry) -> None:
    for agent in registry.all():
        assert agent.system_prompt.strip(), f"{agent.name} has an empty prompt"


def test_routing_triple_is_valid(registry: AgentRegistry) -> None:
    for agent in registry.all():
        r = agent.routing()
        assert r["task_kind"] in {"SUMMARIZE", "CLASSIFY", "REASON", "LONG_CONTEXT", "CODE"}
        assert r["budget_hint"] in {"low", "normal", "high"}
        assert r["privacy"] in {"standard", "sensitive", "air_gapped"}


def test_discovery_agents_share_output_schema(registry: AgentRegistry) -> None:
    # The 6 discovery agents reference the shared discovery envelope; it must
    # resolve to a real JSON Schema at load time.
    for name in ("security_analysis", "performance_analysis", "cloud_analysis",
                 "kubernetes", "database", "hardware"):
        agent = registry.get(name)
        assert agent.task_kind == "REASON"
        assert agent.output_schema is not None
        assert agent.output_schema["title"] == "DiscoveryAgentOutput"


def test_no_prescriptive_agents_remain(registry: AgentRegistry) -> None:
    for gone in ("riskrank", "blueprint", "verification"):
        assert gone not in registry, f"{gone} should have been removed"


def test_report_uses_long_context(registry: AgentRegistry) -> None:
    assert registry.get("report").task_kind == "LONG_CONTEXT"


def test_missing_dir_raises() -> None:
    with pytest.raises(AgentSpecError):
        AgentRegistry.load(Path("/nonexistent/agents"))


def test_unknown_agent_lookup_raises(registry: AgentRegistry) -> None:
    with pytest.raises(KeyError):
        registry.get("does_not_exist")
