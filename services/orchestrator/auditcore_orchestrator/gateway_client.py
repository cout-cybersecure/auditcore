"""Client for the model-gateway. Abstracted behind a Protocol so the discovery
core can be unit-tested with a fake (no network)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class GatewayResult:
    parsed: dict[str, Any] | None
    schema_valid: bool | None
    schema_errors: list[str]
    model: str
    provider: str
    cost_usd: float
    content: str


class GatewayClient(Protocol):
    async def complete(
        self,
        *,
        task_kind: str,
        system_prompt: str,
        user_content: str,
        output_schema: dict[str, Any] | None,
        tenant_id: str,
        agent: str,
        budget_hint: str,
        privacy: str,
    ) -> GatewayResult: ...


class HttpGatewayClient:
    """Talks to the running model-gateway service over HTTP."""

    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def complete(
        self,
        *,
        task_kind: str,
        system_prompt: str,
        user_content: str,
        output_schema: dict[str, Any] | None,
        tenant_id: str,
        agent: str,
        budget_hint: str,
        privacy: str,
    ) -> GatewayResult:
        body = {
            "task_kind": task_kind,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "output_schema": output_schema,
            "tenant_id": tenant_id,
            "agent": agent,
            "budget_hint": budget_hint,
            "privacy": privacy,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(f"{self._base_url}/v1/complete", json=body)
            r.raise_for_status()
            data = r.json()
        return GatewayResult(
            parsed=data.get("parsed"),
            schema_valid=data.get("schema_valid"),
            schema_errors=data.get("schema_errors", []),
            model=data.get("model", ""),
            provider=data.get("provider", ""),
            cost_usd=data.get("cost_usd", 0.0),
            content=data.get("content", ""),
        )
