from uuid import UUID

import pytest

from auditcore_scoring import RawSubScores, ScoringEngine


def _raw(**overrides):
    base = dict(
        finding_id=UUID("00000000-0000-0000-0000-000000000001"),
        exposure=5, exploitability=5, asset_importance=3,
        blast_radius=5, business_impact=5, fix_difficulty=3,
        confidence=1.0, rationale="test",
    )
    base.update(overrides)
    return RawSubScores(**base)


def test_clamps_out_of_range_values():
    eng = ScoringEngine()
    [r] = eng.score([_raw(exposure=99, fix_difficulty=0)])
    assert r.exposure == 10
    assert r.fix_difficulty == 1
    assert "exposure" in r.clamped_fields
    assert "fix_difficulty" in r.clamped_fields


def test_critical_finding_scores_high():
    eng = ScoringEngine()
    [r] = eng.score([_raw(
        exposure=10, exploitability=10, asset_importance=5,
        blast_radius=10, business_impact=10, fix_difficulty=1, confidence=1.0,
    )])
    # max possible composite is 100 with this formula
    assert r.composite >= 90, r.composite


def test_ranking_is_deterministic():
    eng = ScoringEngine()
    a = _raw(finding_id=UUID("00000000-0000-0000-0000-00000000000a"), exposure=2)
    b = _raw(finding_id=UUID("00000000-0000-0000-0000-00000000000b"), exposure=9)
    c = _raw(finding_id=UUID("00000000-0000-0000-0000-00000000000c"), exposure=5)

    scored = eng.score([a, b, c])
    assert scored[0].finding_id == b.finding_id
    assert scored[-1].finding_id == a.finding_id
    # tie-break: a deterministic order even when composites match
    a2 = _raw(finding_id=UUID("00000000-0000-0000-0000-000000000001"), exposure=5)
    a3 = _raw(finding_id=UUID("00000000-0000-0000-0000-000000000002"), exposure=5)
    pair = eng.score([a3, a2])
    assert pair[0].finding_id < pair[1].finding_id


def test_confidence_zero_zeroes_out_composite():
    eng = ScoringEngine()
    [r] = eng.score([_raw(confidence=0.0, exposure=10, exploitability=10)])
    assert r.composite == 0.0


@pytest.mark.parametrize("conf", [0.25, 0.5, 0.75, 1.0])
def test_confidence_scales_linearly(conf: float):
    eng = ScoringEngine()
    [base] = eng.score([_raw(confidence=1.0)])
    [scaled] = eng.score([_raw(confidence=conf)])
    assert abs(scaled.composite - base.composite * conf) < 0.01
