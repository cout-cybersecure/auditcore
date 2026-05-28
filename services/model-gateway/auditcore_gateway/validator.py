"""JSON Schema validation + best-effort JSON extraction.

Agents often return JSON inside a markdown code fence; we strip those.
"""
from __future__ import annotations

import json
import re
from typing import Any

import jsonschema

_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL,
)


def extract_json(text: str) -> Any | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    # Fallback: find the first balanced {...} or [...] block.
    for opener, closer in [("{", "}"), ("[", "]")]:
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def validate(parsed: Any, schema: dict[str, Any]) -> list[str]:
    """Return a list of validation errors; empty if valid."""
    validator = jsonschema.Draft202012Validator(schema)
    errs = sorted(validator.iter_errors(parsed), key=lambda e: list(e.path))
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errs]
