"""Local-model provider — speaks the OpenAI-compatible chat completions API.

Works against llama.cpp's `server`, vLLM, Ollama (with the openai endpoint),
and most other inference servers in common use.
"""
from __future__ import annotations

import time

import httpx

from ..config import settings
from ..types import Message, ModelResponse


class LocalProvider:
    name = "local"

    async def complete(
        self,
        messages: list[Message],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ModelResponse:
        url = f"{settings.local_endpoint.rstrip('/')}/v1/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return ModelResponse(
            content=text,
            provider=self.name,
            model=model,
            tier_used="primary",
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
        )
