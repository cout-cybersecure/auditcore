"""Render the AI-narrated report_sections produced by the report agent.

The report agent's section bodies reference observations with
`[[observation:UUID]]` markers. Here we expand each marker to the observation's
topic (and keep the id as a hover/title), so the narrated document stays
traceable to discovered facts. Unknown ids are rendered as an explicit
`(unknown observation)` marker rather than silently dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .render import _env  # reuse the configured Jinja env + md filter

_OBS_REF = re.compile(r"\[\[observation:([0-9a-fA-F-]{36})\]\]")


@dataclass(frozen=True)
class SectionsData:
    run: dict[str, Any]
    sections: list[dict[str, Any]]          # each: audience, order, title, body_md
    observation_topics: dict[str, str]      # observation_id -> topic


def expand_markers(body_md: str, topics: dict[str, str]) -> str:
    """Replace [[observation:UUID]] with a readable, traceable inline cite."""
    def repl(m: re.Match[str]) -> str:
        oid = m.group(1)
        topic = topics.get(oid)
        if topic:
            # Markdown abbreviation-style: topic with the id retained in title.
            return f"*{topic}*"
        return "*(unknown observation)*"
    return _OBS_REF.sub(repl, body_md)


def render_sections_html(data: SectionsData, audience: str) -> str:
    if audience not in ("technical", "summary"):
        raise ValueError(f"unknown audience: {audience}")
    sections = sorted(
        (s for s in data.sections if s["audience"] == audience),
        key=lambda s: s["order"],
    )
    expanded = [
        {**s, "body_md": expand_markers(s["body_md"], data.observation_topics)}
        for s in sections
    ]
    tpl = _env.get_template("sections.html.j2")
    return tpl.render(
        data=data,
        audience=audience,
        sections=expanded,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
