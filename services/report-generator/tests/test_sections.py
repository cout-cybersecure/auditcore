"""Tests for the agent-narrated report_sections renderer (no DB)."""
from auditcore_report.sections import SectionsData, expand_markers, render_sections_html

OID = "30000000-0000-0000-0000-000000000001"
UNKNOWN = "99999999-9999-9999-9999-999999999999"


def _data() -> SectionsData:
    return SectionsData(
        run={"id": "00000000-0000-0000-0000-000000000001",
             "status": "complete", "started_at": "2026-05-27T00:00:00Z"},
        sections=[
            {"audience": "technical", "order": 1, "title": "Networking",
             "body_md": "Two interfaces are present."},
            {"audience": "technical", "order": 0, "title": "Hardware",
             "body_md": f"The host has 16 CPUs [[observation:{OID}]]."},
            {"audience": "summary", "order": 0, "title": "Overview",
             "body_md": "A single-socket Linux host."},
        ],
        observation_topics={OID: "CPU topology"},
    )


def test_expand_known_marker_to_topic():
    out = expand_markers(f"see [[observation:{OID}]] here", {OID: "CPU topology"})
    assert "CPU topology" in out
    assert "[[observation" not in out


def test_expand_unknown_marker_is_explicit():
    out = expand_markers(f"see [[observation:{UNKNOWN}]] here", {OID: "CPU topology"})
    assert "unknown observation" in out


def test_render_orders_sections_and_filters_audience():
    html = render_sections_html(_data(), audience="technical")
    # Hardware (order 0) must appear before Networking (order 1).
    assert html.index("Hardware") < html.index("Networking")
    # Summary-only section is excluded from the technical render.
    assert "Overview" not in html
    # Marker expanded to the topic.
    assert "CPU topology" in html


def test_render_summary_audience():
    html = render_sections_html(_data(), audience="summary")
    assert "Overview" in html
    assert "Networking" not in html


def test_invalid_audience_raises():
    import pytest
    with pytest.raises(ValueError):
        render_sections_html(_data(), audience="executive")
