"""Load and validate agent definitions from the agents/ directory.

An agent definition lives at agents/<name>/ with:
    agent.yaml          — spec (routing, contract, paths)
    prompts/system.md   — system prompt
    schemas/output.json — JSON Schema the output must validate against
                          (may be a relative path to a shared schema)

The registry is the single source of truth the orchestrator uses to invoke
agents. It resolves prompt + schema paths at load time and fails fast on a
malformed definition.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Task kinds accepted by the model gateway. Kept as a plain set so this package
# does not need to depend on the gateway package.
VALID_TASK_KINDS = {"SUMMARIZE", "CLASSIFY", "REASON", "LONG_CONTEXT", "CODE"}
VALID_BUDGETS = {"low", "normal", "high"}
VALID_PRIVACY = {"standard", "sensitive", "air_gapped"}


class AgentSpecError(Exception):
    """Raised when an agent definition is malformed or inconsistent."""


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    version: str
    purpose: str
    task_kind: str
    budget_hint: str
    privacy: str
    system_prompt: str            # resolved prompt text
    output_schema: dict[str, Any] | None   # resolved JSON Schema, or None
    contract: tuple[str, ...]
    directory: Path

    def routing(self) -> dict[str, str]:
        """The triple the model gateway needs to resolve a concrete model."""
        return {
            "task_kind": self.task_kind,
            "budget_hint": self.budget_hint,
            "privacy": self.privacy,
        }


class AgentRegistry:
    def __init__(self, agents: dict[str, AgentDefinition]) -> None:
        self._agents = agents

    def __contains__(self, name: str) -> bool:
        return name in self._agents

    def __len__(self) -> int:
        return len(self._agents)

    def names(self) -> list[str]:
        return sorted(self._agents)

    def get(self, name: str) -> AgentDefinition:
        if name not in self._agents:
            raise KeyError(f"no such agent: {name!r} (have: {self.names()})")
        return self._agents[name]

    def all(self) -> list[AgentDefinition]:
        return [self._agents[n] for n in self.names()]

    @classmethod
    def load(cls, agents_dir: Path) -> "AgentRegistry":
        if not agents_dir.is_dir():
            raise AgentSpecError(f"agents dir not found: {agents_dir}")

        agents: dict[str, AgentDefinition] = {}
        for child in sorted(agents_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            spec_path = child / "agent.yaml"
            if not spec_path.exists():
                continue
            definition = _load_one(child, spec_path)
            agents[definition.name] = definition

        if not agents:
            raise AgentSpecError(f"no agent definitions found under {agents_dir}")
        return cls(agents)


def _load_one(directory: Path, spec_path: Path) -> AgentDefinition:
    raw = yaml.safe_load(spec_path.read_text())
    if not isinstance(raw, dict):
        raise AgentSpecError(f"{spec_path}: top-level YAML must be a mapping")

    name = _require(raw, "name", spec_path)
    if name != directory.name:
        raise AgentSpecError(
            f"{spec_path}: name {name!r} does not match directory {directory.name!r}"
        )

    task_kind = _require(raw, "task_kind", spec_path)
    if task_kind not in VALID_TASK_KINDS:
        raise AgentSpecError(
            f"{spec_path}: task_kind {task_kind!r} not in {sorted(VALID_TASK_KINDS)}"
        )

    budget = raw.get("budget_hint", "normal")
    if budget not in VALID_BUDGETS:
        raise AgentSpecError(f"{spec_path}: budget_hint {budget!r} invalid")

    privacy = raw.get("privacy", "standard")
    if privacy not in VALID_PRIVACY:
        raise AgentSpecError(f"{spec_path}: privacy {privacy!r} invalid")

    system_prompt = _resolve_prompt(directory, raw.get("system_prompt"), spec_path)
    output_schema = _resolve_schema(directory, raw.get("output_schema"), spec_path)

    contract = tuple(raw.get("contract", []) or [])

    return AgentDefinition(
        name=name,
        version=str(raw.get("version", "0.0.0")),
        purpose=str(raw.get("purpose", "")).strip(),
        task_kind=task_kind,
        budget_hint=budget,
        privacy=privacy,
        system_prompt=system_prompt,
        output_schema=output_schema,
        contract=contract,
        directory=directory,
    )


def _require(raw: dict, key: str, spec_path: Path) -> str:
    if key not in raw or raw[key] in (None, ""):
        raise AgentSpecError(f"{spec_path}: missing required key {key!r}")
    return str(raw[key])


def _resolve_prompt(directory: Path, value: str | None, spec_path: Path) -> str:
    if not value:
        raise AgentSpecError(f"{spec_path}: system_prompt is required")
    prompt_path = (directory / value).resolve()
    if not prompt_path.exists():
        raise AgentSpecError(f"{spec_path}: system_prompt file not found: {value}")
    return prompt_path.read_text()


def _resolve_schema(
    directory: Path, value: str | None, spec_path: Path,
) -> dict[str, Any] | None:
    if not value:
        return None
    schema_path = (directory / value).resolve()
    if not schema_path.exists():
        raise AgentSpecError(f"{spec_path}: output_schema file not found: {value}")
    try:
        return json.loads(schema_path.read_text())
    except json.JSONDecodeError as e:
        raise AgentSpecError(f"{spec_path}: output_schema is not valid JSON: {e}") from e
