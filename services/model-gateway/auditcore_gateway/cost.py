"""Cost accounting for model calls.

Per-token pricing lives in `pricing.yaml` next to the routing config.
"""
from __future__ import annotations

from pathlib import Path

import yaml


class CostBook:
    def __init__(self, table: dict[str, dict[str, dict[str, float]]]) -> None:
        # table[provider][model] = {"input_per_1m": X, "output_per_1m": Y}
        self._table = table

    @classmethod
    def from_yaml(cls, path: Path) -> "CostBook":
        if not path.exists():
            return cls({})
        with path.open() as f:
            return cls(yaml.safe_load(f) or {})

    def cost_usd(
        self, provider: str, model: str, input_tokens: int, output_tokens: int,
    ) -> float:
        rates = self._table.get(provider, {}).get(model)
        if not rates:
            return 0.0
        return (
            input_tokens  * rates.get("input_per_1m",  0.0) / 1_000_000
            + output_tokens * rates.get("output_per_1m", 0.0) / 1_000_000
        )
