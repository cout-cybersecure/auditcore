from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import UUID

import click

from .loader import load_run
from .render import render_html, render_pdf

DEFAULT_DSN = os.environ.get(
    "AUDITCORE_DB_DSN",
    "postgresql://auditcore:dev-only-change-me@localhost:5432/auditcore",
)


@click.group()
def main() -> None:
    """AuditCore report generator (manual, non-AI)."""


@main.command()
@click.argument("run_id")
@click.option("--dsn", default=DEFAULT_DSN, show_default=True)
@click.option("--audience", type=click.Choice(["technical", "summary"]),
              default="technical", show_default=True)
@click.option("--out", "out_path", type=click.Path(dir_okay=False, path_type=Path),
              default=None, help="output file (defaults to stdout)")
@click.option("--pdf", is_flag=True, help="render PDF instead of HTML (needs the pdf extra)")
def render(run_id: str, dsn: str, audience: str, out_path: Path | None, pdf: bool) -> None:
    """Render a report for a single run."""
    data = load_run(dsn, UUID(run_id))
    html = render_html(data, audience=audience)
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
