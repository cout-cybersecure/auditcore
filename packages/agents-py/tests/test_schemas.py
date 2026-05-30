"""Guards on the agent output schemas themselves.

Every agent that declares an output_schema must declare a *valid* JSON Schema,
and the shared discovery envelope must actually enforce the evidence-citation
rule that the whole tool depends on.
"""
from pathlib import Path

import jsonschema
import pytest
from auditcore_agents import AgentRegistry

AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"

DISCOVERY_AGENTS = {
    "security_analysis", "performance_analysis", "cloud_analysis",
    "kubernetes", "database", "hardware",
}


@pytest.fixture(scope="module")
def registry() -> AgentRegistry:
    return AgentRegistry.load(AGENTS_DIR)


def test_every_declared_schema_is_valid_draft202012(registry: AgentRegistry) -> None:
    for agent in registry.all():
        if agent.output_schema is None:
            continue
        # Raises SchemaError if the schema itself is malformed.
        jsonschema.Draft202012Validator.check_schema(agent.output_schema)


def test_discovery_agents_use_discovery_envelope(registry: AgentRegistry) -> None:
    for name in DISCOVERY_AGENTS:
        schema = registry.get(name).output_schema
        assert schema is not None
        assert schema["title"] == "DiscoveryAgentOutput"


def test_discovery_schema_requires_evidence_ids(registry: AgentRegistry) -> None:
    schema = registry.get("hardware").output_schema
    validator = jsonschema.Draft202012Validator(schema)

    good = {"observations": [{
        "asset_id": "10000000-0000-0000-0000-000000000001",
        "topic": "CPU", "summary": "16 CPUs", "detail": "details",
        "evidence_ids": ["20000000-0000-0000-0000-000000000001"],
    }]}
    assert validator.is_valid(good)

    # An observation with no evidence must be rejected by the schema.
    no_evidence = {"observations": [{
        "asset_id": "10000000-0000-0000-0000-000000000001",
        "topic": "CPU", "summary": "16 CPUs", "detail": "details",
        "evidence_ids": [],
    }]}
    assert not validator.is_valid(no_evidence)


def test_report_schema_uses_descriptive_audiences(registry: AgentRegistry) -> None:
    schema = registry.get("report").output_schema
    audience_enum = (
        schema["properties"]["sections"]["items"]["properties"]["audience"]["enum"]
    )
    assert set(audience_enum) == {"technical", "summary"}
