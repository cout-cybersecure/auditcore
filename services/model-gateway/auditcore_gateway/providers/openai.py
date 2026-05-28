from __future__ import annotations

import time

from ..config import settings
from ..types import Message, ModelResponse


class OpenAIProvider:
    name = "openai"

    async def complete(
        self,
        messages: list[Message],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ModelResponse:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key or None)
        conv = [{"role": m.role, "content": m.content} for m in messages]

        t0 = time.perf_counter()
        resp = await client.chat.completions.create(
            model=model,
            messages=conv,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return ModelResponse(
            content=text,
            provider=self.name,
            model=model,
            tier_used="primary",
            input_tokens=getattr(usage, "prompt_tokens", 0),
            output_tokens=getattr(usage, "completion_tokens", 0),
            latency_ms=latency_ms,
        )
