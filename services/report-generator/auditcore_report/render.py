"""Manual (non-AI) report renderer.

Phase 1 exit criterion: produce a readable HTML report directly from
normalized data, with NO AI involvement. Phase 2 adds the Report Agent
narrative on top.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt

TEMPLATES = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_md = MarkdownIt("commonmark", {"breaks": False, "html": False}).enable("table")
_env.filters["md"] = _md.render


@dataclass(frozen=True)
class ReportData:
    run: dict[str, Any]
    assets: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    blueprints: list[dict[str, Any]]


def render_html(data: ReportData, audience: str = "engineer") -> str:
    if audience not in ("engineer", "executive"):
        raise ValueError(f"unknown audience: {audience}")
    tpl = _env.get_template(f"{audience}.html.j2")
    return tpl.render(
        data=data,
        generated_at=datetime.now(timezone.utc).isoformat(),
        severity_counts=_severity_counts(data.findings),
    )


def render_pdf(html: str) -> bytes:
    """Render HTML to PDF. Requires the `pdf` extra (WeasyPrint)."""
    try:
        from weasyprint import HTML
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "PDF rendering requires the `pdf` extra: "
            "pip install auditcore-report-generator[pdf]"
        ) from e
    return HTML(string=html).write_pdf()


def _severity_counts(findings: list[dict]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        counts[f.get("severity", "info")] = counts.get(f.get("severity", "info"), 0) + 1
    return counts
