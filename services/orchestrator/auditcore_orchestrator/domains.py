"""Maps evidence categories to discovery domains and the agent that handles them.

Evidence `category` values are produced by parsers/connectors. Each maps to a
`domain` (the Observation.domain enum value) and the discovery agent name.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainBinding:
    domain: str       # Observation.domain value
    agent: str        # agent registry name


# evidence category -> binding
CATEGORY_BINDINGS: dict[str, DomainBinding] = {
    "security":   DomainBinding("security",    "security_analysis"),
    "performance":DomainBinding("performance", "performance_analysis"),
    "cloud":      DomainBinding("cloud",       "cloud_analysis"),
    "kubernetes": DomainBinding("k8s",         "kubernetes"),
    "database":   DomainBinding("db",          "database"),
    "hardware":   DomainBinding("hardware",    "hardware"),
    # Inventory facts (uname, etc.) are described by the hardware agent.
    "inventory":  DomainBinding("hardware",    "hardware"),
}


def binding_for(category: str) -> DomainBinding | None:
    return CATEGORY_BINDINGS.get(category)
