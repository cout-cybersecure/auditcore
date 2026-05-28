"""Connector base class — pull-mode integrations on the control plane."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Target:
    """Identifies the thing a connector is asked to read."""
    identifier: str                     # AWS account id, kubeconfig context, DSN, scrape URL
    credentials_ref: str | None = None  # Vault path or env var name; never the secret itself
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceBlob:
    """One raw artifact ready for the same ingestion path as a collector bundle item."""
    source_tool: str
    source_tool_version: str
    category: str               # security | performance | cloud | kubernetes | database | hardware | inventory
    collected_at: datetime
    raw: bytes                  # the original tool output
    id: UUID = field(default_factory=uuid4)
    scope: dict[str, Any] = field(default_factory=dict)


class Connector(ABC):
    """Subclasses must set `name` and `category` and implement `collect`."""
    name: str = ""
    category: str = ""

    @abstractmethod
    async def collect(self, target: Target) -> list[EvidenceBlob]:
        """Return one EvidenceBlob per logical artifact produced."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "name", "") or not getattr(cls, "category", ""):
            raise TypeError(
                f"{cls.__name__} must set class attributes `name` and `category`"
            )
