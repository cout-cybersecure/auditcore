"""Renderer tests that don't need a real database."""
from auditcore_report.render import ReportData, render_html


def _data() -> ReportData:
    return ReportData(
        run={
            "id": "00000000-0000-0000-0000-000000000001",
            "status": "complete",
            "scope": {"hostname": "host-a"},
            "started_at": "2026-05-27T00:00:00Z",
            "completed_at": "2026-05-27T00:05:00Z",
            "cost_cents": 0,
        },
        assets=[{
            "id": "10000000-0000-0000-0000-000000000001",
            "type": "host", "natural_key": "host:abc", "name": "host-a",
            "attributes": {"cpu_model": "Xeon Gold 6226R", "architecture": "x86_64"},
        }],
        evidence=[{
            "id": "20000000-0000-0000-0000-000000000001",
            "asset_id": "10000000-0000-0000-0000-000000000001",
            "source_tool": "lscpu", "source_tool_version": "util-linux 2.39",
            "category": "hardware", "parsed": {"CPU(s)": 16},
            "confidence": 0.95,
            "collected_at": "2026-05-27T00:00:01Z",
        }],
        observations=[{
            "id": "30000000-0000-0000-0000-000000000001",
            "asset_id": "10000000-0000-0000-0000-000000000001",
            "domain": "hardware",
            "topic": "CPU topology",
            "summary": "16 logical CPUs across 1 socket, 8 cores, 2 threads/core",
            "detail": "The host presents a single-socket Intel Xeon Gold 6226R with "
                      "8 physical cores and 2 threads per core (16 logical CPUs).",
            "facts": {"sockets": 1, "cores_per_socket": 8, "threads_per_core": 2},
            "related_asset_ids": [],
            "evidence_ids": ["20000000-0000-0000-0000-000000000001"],
            "produced_by_agent": "hardware@0.2.0",
        }],
    )


def test_technical_renders():
    html = render_html(_data(), audience="technical")
    assert "System Description" in html
    assert "host-a" in html
    assert "CPU topology" in html
    assert "lscpu" in html
    # No risk/severity vocabulary anywhere in the descriptive output.
    for word in ("severity", "critical", "risk", "recommend"):
        assert word.lower() not in html.lower(), f"{word!r} leaked into descriptive report"


def test_summary_renders():
    html = render_html(_data(), audience="summary")
    assert "System Summary" in html
    assert "Key functional characteristics" in html
    assert "CPU topology" in html


def test_invalid_audience_raises():
    import pytest
    with pytest.raises(ValueError):
        render_html(_data(), audience="executive")
