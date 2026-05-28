"""Resolve `(task_kind, budget_hint, privacy)` to a concrete provider+model.

Reads the YAML routing table at startup. Privacy overrides always win
over budget.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .types import BudgetTier, PrivacyTier, RouteDecision, TaskKind

log = logging.getLogger(__name__)


class RoutingError(Exception):
    pass


class Router:
    def __init__(self, table: dict[str, Any]) -> None:
        self._table = table

    @classmethod
    def from_yaml(cls, path: Path) -> "Router":
        with path.open() as f:
            return cls(yaml.safe_load(f))

    def resolve(
        self,
        task_kind: TaskKind,
        budget: BudgetTier,
        privacy: PrivacyTier,
    ) -> RouteDecision:
        # Air-gapped: provider-locked routes.
        if privacy == "air_gapped":
            override = self._table.get("privacy_overrides", {}).get("air_gapped", {})
            routes = override.get("routes", {}).get(task_kind.value)
            if not routes:
                raise RoutingError(
                    f"no air_gapped route defined for task_kind={task_kind}"
                )
            primary = self._slot(routes["primary"])
            return RouteDecision(primary=primary)

        slot = self._table["defaults"][task_kind.value][budget]
        primary = self._slot(slot["primary"])
        secondary = self._slot(slot["secondary"]) if "secondary" in slot else None
        tertiary = self._slot(slot["tertiary"]) if "tertiary" in slot else None
        critic = bool(slot.get("primary", {}).get("critic_loop", False))

        if privacy == "sensitive":
            denied = set(
                self._table.get("privacy_overrides", {})
                          .get("sensitive", {})
                          .get("deny_providers", [])
            )
            primary, secondary, tertiary = self._drop_denied(
                primary, secondary, tertiary, denied,
            )

        return RouteDecision(
            primary=primary,
            secondary=secondary,
            tertiary=tertiary,
            critic_loop=critic,
        )

    @staticmethod
    def _slot(slot: dict[str, Any]) -> tuple[str, str]:
        return slot["provider"], slot["model"]

    @staticmethod
    def _drop_denied(
        primary: tuple[str, str],
        secondary: tuple[str, str] | None,
        tertiary: tuple[str, str] | None,
        denied: set[str],
    ) -> tuple[tuple[str, str], tuple[str, str] | None, tuple[str, str] | None]:
        chain = [s for s in (primary, secondary, tertiary)
                 if s is not None and s[0] not in denied]
        if not chain:
            raise RoutingError(
                "privacy=sensitive removed every routed provider for this slot"
            )
        return (
            chain[0],
            chain[1] if len(chain) > 1 else None,
            chain[2] if len(chain) > 2 else None,
        )

    def fallback_settings(self) -> dict[str, Any]:
        return self._table.get("fallback", {})

    def cost_caps(self) -> dict[str, Any]:
        return self._table.get("cost_caps", {})
