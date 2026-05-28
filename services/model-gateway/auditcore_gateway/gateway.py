"""Orchestrates routing + fallback + cost accounting + output validation."""
from __future__ import annotations

import logging
import time

from .cost import CostBook
from .providers import get_provider
from .routing import Router
from .types import CompleteRequest, ModelResponse, RouteDecision

log = logging.getLogger(__name__)


class Gateway:
    def __init__(self, router: Router, costs: CostBook) -> None:
        self.router = router
        self.costs = costs

    async def complete(self, req: CompleteRequest) -> ModelResponse:
        route = self.router.resolve(req.task_kind, req.budget_hint, req.privacy)
        attempts: list[tuple[str, tuple[str, str]]] = []
        for tier_name in ("primary", "secondary", "tertiary"):
            target = getattr(route, tier_name)
            if target is not None:
                attempts.append((tier_name, target))

        escalate_on_schema_failure = bool(
            self.router.fallback_settings().get("escalate_on_schema_failure", False)
        )

        last_err: Exception | None = None
        for tier_name, (provider_name, model) in attempts:
            try:
                resp = await self._call(req, route, provider_name, model)
                resp.tier_used = tier_name  # type: ignore[assignment]

                if req.output_schema:
                    self._attach_validation(resp, req.output_schema)
                    if resp.schema_valid is False and escalate_on_schema_failure:
                        log.warning(
                            "schema validation failed on %s/%s tier=%s; escalating",
                            provider_name, model, tier_name,
                        )
                        last_err = RuntimeError("schema validation failed")
                        continue
                return resp
            except Exception as e:  # noqa: BLE001 — fallback covers all provider errors
                log.warning("provider %s/%s failed (tier=%s): %s",
                            provider_name, model, tier_name, e)
                last_err = e
                continue

        raise RuntimeError(
            f"all routing tiers exhausted for task_kind={req.task_kind}: {last_err}"
        )

    async def _call(
        self,
        req: CompleteRequest,
        route: RouteDecision,                  # noqa: ARG002 — reserved for critic loop
        provider_name: str,
        model: str,
    ) -> ModelResponse:
        provider = get_provider(provider_name)
        t0 = time.perf_counter()
        resp = await provider.complete(
            req.messages, model, req.max_tokens, req.temperature,
        )
        resp.latency_ms = int((time.perf_counter() - t0) * 1000)
        resp.cost_usd = self.costs.cost_usd(
            provider_name, model, resp.input_tokens, resp.output_tokens,
        )
        return resp

    @staticmethod
    def _attach_validation(resp: ModelResponse, schema: dict) -> None:
        from .validator import extract_json, validate
        parsed = extract_json(resp.content)
        if parsed is None:
            resp.schema_valid = False
            resp.schema_errors = ["model output was not valid JSON"]
            return
        errors = validate(parsed, schema)
        resp.parsed = parsed if not errors else None
        resp.schema_valid = not errors
        resp.schema_errors = errors
