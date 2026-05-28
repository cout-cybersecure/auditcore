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
            "severity_hint": None, "confidence": 0.95,
            "collected_at": "2026-05-27T00:00:01Z",
        }],
        findings=[{
            "id": "30000000-0000-0000-0000-000000000001",
            "asset_id": "10000000-0000-0000-0000-000000000001",
            "domain": "performance",
            "title": "CPU saturation observed",
            "description": "Sustained 95% utilization.",
            "severity": "high",
            "cwe": [], "cve": [], "cis_controls": [],
            "evidence_ids": ["20000000-0000-0000-0000-000000000001"],
            "produced_by_agent": "performance_analysis@0.1.0",
        }],
        blueprints=[],
    )


def test_engineer_renders():
    html = render_html(_data(), audience="engineer")
    assert "Engineer Report" in html
    assert "host-a" in html
    assert "sev-high" in html
    assert "lscpu" in html


def test_executive_renders():
    html = render_html(_data(), audience="executive")
    assert "Executive Report" in html
    assert "Top findings" in html


def test_invalid_audience_raises():
    import pytest
    with pytest.raises(ValueError):
        render_html(_data(), audience="legal")
