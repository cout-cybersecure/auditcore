"""Manual (non-AI) report renderer.

Produces a precise, exhaustive description of the assessed system directly
from normalized data — assets, evidence, and discovered observations — with
NO AI involvement. The Report Agent (Phase 2) produces a narrated version of
the same facts; this renderer is the deterministic floor.

The output is purely descriptive: what exists and how it works. There is no
severity, score, or recommendation anywhere.
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

# Discovery domains, in the order they appear in the technical document.
DOMAIN_ORDER = [
    "hardware", "software", "network", "security",
    "performance", "cloud", "k8s", "db",
]
DOMAIN_LABELS = {
    "hardware": "Hardware", "software": "Software", "network": "Network",
    "security": "Security", "performance": "Performance", "cloud": "Cloud",
    "k8s": "Kubernetes", "db": "Database",
}


@dataclass(frozen=True)
class ReportData:
    run: dict[str, Any]
    assets: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    observations: list[dict[str, Any]]


def render_html(data: ReportData, audience: str = "technical") -> str:
    if audience not in ("technical", "summary"):
        raise ValueError(f"unknown audience: {audience}")
    tpl = _env.get_template(f"{audience}.html.j2")
    return tpl.render(
        data=data,
        generated_at=datetime.now(timezone.utc).isoformat(),
        domains=_observations_by_domain(data.observations),
        domain_labels=DOMAIN_LABELS,
        evidence_by_category=_count_by(data.evidence, "category"),
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


def _observations_by_domain(
    observations: list[dict],
) -> list[tuple[str, list[dict]]]:
    """Group observations by domain in DOMAIN_ORDER; omit empty domains."""
    grouped: dict[str, list[dict]] = {}
    for obs in observations:
        grouped.setdefault(obs.get("domain", "software"), []).append(obs)
    ordered: list[tuple[str, list[dict]]] = []
    for domain in DOMAIN_ORDER:
        if grouped.get(domain):
            ordered.append((domain, grouped[domain]))
    # Any domain not in DOMAIN_ORDER (forward-compat) appended at the end.
    for domain, items in grouped.items():
        if domain not in DOMAIN_LABELS:
            ordered.append((domain, items))
    return ordered


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r.get(key, "unknown")] = out.get(r.get(key, "unknown"), 0) + 1
    return dict(sorted(out.items()))
