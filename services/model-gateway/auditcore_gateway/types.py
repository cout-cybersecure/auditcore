"""Shared types for the model gateway."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskKind(str, Enum):
    SUMMARIZE = "SUMMARIZE"
    CLASSIFY = "CLASSIFY"
    REASON = "REASON"
    LONG_CONTEXT = "LONG_CONTEXT"
    CODE = "CODE"


BudgetTier = Literal["low", "normal", "high"]
PrivacyTier = Literal["standard", "sensitive", "air_gapped"]


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class CompleteRequest(BaseModel):
    task_kind: TaskKind
    messages: list[Message]
    output_schema: dict[str, Any] | None = None
    tenant_id: str
    budget_hint: BudgetTier = "normal"
    privacy: PrivacyTier = "standard"
    # Identifier for the agent making the call (audit + cost attribution).
    agent: str = "unknown"
    # Pass-through to providers; gateway clamps to a sane ceiling.
    max_tokens: int = Field(default=4096, ge=1, le=200_000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class ModelResponse(BaseModel):
    content: str
    parsed: dict[str, Any] | None = None
    provider: str
    model: str
    tier_used: Literal["primary", "secondary", "tertiary"]
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    schema_valid: bool | None = None
    schema_errors: list[str] = Field(default_factory=list)


class RouteDecision(BaseModel):
    """The concrete provider/model the router resolved to, plus fallbacks."""
    primary: tuple[str, str]
    secondary: tuple[str, str] | None = None
    tertiary: tuple[str, str] | None = None
    critic_loop: bool = False
