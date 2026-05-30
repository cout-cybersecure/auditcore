"""Regenerate canonical JSON Schema artifacts in /schemas from the Pydantic models.

Run from anywhere:
    python packages/models-py/scripts/generate_schemas.py
"""
from __future__ import annotations

import json
from pathlib import Path

from auditcore_models import (
    Asset,
    EvidenceItem,
    Observation,
    ReportSection,
    Run,
)

MODELS = [
    Run, Asset, EvidenceItem, Observation, ReportSection,
]

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT = REPO_ROOT / "schemas"


def to_snake(name: str) -> str:
    out: list[str] = []
    for i, c in enumerate(name):
        if c.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(c.lower())
    return "".join(out)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    index: dict[str, str] = {}
    for model in MODELS:
        schema = model.model_json_schema()
        schema["$id"] = f"https://schemas.auditcore.dev/v1/{to_snake(model.__name__)}.json"
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        out_path = OUT / f"{to_snake(model.__name__)}.json"
        out_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        index[model.__name__] = out_path.relative_to(REPO_ROOT).as_posix()
        print(f"wrote {out_path.relative_to(REPO_ROOT)}")
    (OUT / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    print(f"wrote {(OUT / 'index.json').relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
