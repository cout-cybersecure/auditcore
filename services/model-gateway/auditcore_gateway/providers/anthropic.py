from __future__ import annotations

import time

from ..config import settings
from ..types import Message, ModelResponse


class AnthropicProvider:
    name = "anthropic"

    async def complete(
        self,
        messages: list[Message],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ModelResponse:
        # Lazy import — only fail if this provider is actually routed to.
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)

        system = "\n\n".join(m.content for m in messages if m.role == "system") or None
        conv = [{"role": m.role, "content": m.content}
                for m in messages if m.role != "system"]

        t0 = time.perf_counter()
        resp = await client.messages.create(
            model=model,
            system=system,
            messages=conv,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        usage = resp.usage
        return ModelResponse(
            content=text,
            provider=self.name,
            model=model,
            tier_used="primary",  # caller overrides if this came from a fallback
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            latency_ms=latency_ms,
        )
