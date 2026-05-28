from __future__ import annotations

import time

from ..config import settings
from ..types import Message, ModelResponse


class GoogleProvider:
    name = "google"

    async def complete(
        self,
        messages: list[Message],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ModelResponse:
        import google.generativeai as genai

        genai.configure(api_key=settings.google_api_key or None)
        gmodel = genai.GenerativeModel(model)

        system = "\n\n".join(m.content for m in messages if m.role == "system")
        history = "\n\n".join(
            f"{m.role.upper()}: {m.content}"
            for m in messages if m.role != "system"
        )
        prompt = (system + "\n\n" + history) if system else history

        t0 = time.perf_counter()
        # google-generativeai is sync; offload to a thread.
        import asyncio
        resp = await asyncio.to_thread(
            gmodel.generate_content, prompt,
            generation_config={"max_output_tokens": max_tokens, "temperature": temperature},
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        return ModelResponse(
            content=resp.text or "",
            provider=self.name,
            model=model,
            tier_used="primary",
            input_tokens=getattr(resp.usage_metadata, "prompt_token_count", 0),
            output_tokens=getattr(resp.usage_metadata, "candidates_token_count", 0),
            latency_ms=latency_ms,
        )
