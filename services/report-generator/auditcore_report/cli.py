from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import UUID

import click

from .loader import load_run, load_sections
from .render import render_html, render_pdf
from .sections import render_sections_html

DEFAULT_DSN = os.environ.get(
    "AUDITCORE_DB_DSN",
    "postgresql://auditcore:dev-only-change-me@localhost:5432/auditcore",
)


@click.group()
def main() -> None:
    """AuditCore report generator — descriptive output, facts only."""


@main.command()
@click.argument("run_id")
@click.option("--dsn", default=DEFAULT_DSN, show_default=True)
@click.option("--audience", type=click.Choice(["technical", "summary"]),
              default="technical", show_default=True)
@click.option("--source", type=click.Choice(["observations", "sections"]),
              default="observations", show_default=True,
              help="'observations' = deterministic render from the DB; "
                   "'sections' = the agent-narrated report_sections")
@click.option("--out", "out_path", type=click.Path(dir_okay=False, path_type=Path),
              default=None, help="output file (defaults to stdout)")
@click.option("--pdf", is_flag=True, help="render PDF instead of HTML (needs the pdf extra)")
def render(run_id: str, dsn: str, audience: str, source: str,
           out_path: Path | None, pdf: bool) -> None:
    """Render a descriptive report for a single run."""
    rid = UUID(run_id)
    if source == "sections":
        html = render_sections_html(load_sections(dsn, rid), audience=audience)
    else:
        html = render_html(load_run(dsn, rid), audience=audience)

    payload: bytes | str = render_pdf(html) if pdf else html
    if out_path:
        if isinstance(payload, bytes):
            out_path.write_bytes(payload)
        else:
            out_path.write_text(payload)
        click.echo(f"wrote {out_path}", err=True)
    else:
        if isinstance(payload, bytes):
            sys.stdout.buffer.write(payload)
        else:
            click.echo(payload)


if __name__ == "__main__":  # pragma: no cover
    main()
