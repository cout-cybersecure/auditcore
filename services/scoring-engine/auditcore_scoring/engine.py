"""Deterministic risk scoring.

The RiskRank agent proposes sub-scores; this engine clamps them to bounds
and computes the composite. The agent's authority is only `rationale`.

Formula (from agents/riskrank/agent.yaml — keep these in sync):

    composite = (
        exposure        * 0.25 +
        exploitability  * 0.20 +
        blast_radius    * 0.15 +
        business_impact * 0.20 +
        asset_importance * 2  * 0.10 +     # rescaled to 0-10
        (6 - fix_difficulty) * 2 * 0.10    # easier-to-fix gets nudged up
    ) * confidence * 10                    # final scale 0-100
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RawSubScores:
    finding_id: UUID
    exposure: int           # 0-10
    exploitability: int     # 0-10
    asset_importance: int   # 1-5
    blast_radius: int       # 0-10
    business_impact: int    # 0-10
    fix_difficulty: int     # 1-5 (5 = hard)
    confidence: float       # 0.0-1.0
    rationale: str


@dataclass(frozen=True)
class ScoredFinding:
    finding_id: UUID
    exposure: int
    exploitability: int
    asset_importance: int
    blast_radius: int
    business_impact: int
    fix_difficulty: int
    confidence: float
    composite: float        # 0-100
    rank: int               # 1 = top priority
    rationale: str
    clamped_fields: tuple[str, ...]


def _clamp(value: int | float, lo: int | float, hi: int | float, name: str,
           clamped: list[str]) -> int | float:
    if value < lo:
        clamped.append(name)
        return lo
    if value > hi:
        clamped.append(name)
        return hi
    return value


class ScoringEngine:
    BOUNDS = {
        "exposure":         (0, 10),
        "exploitability":   (0, 10),
        "asset_importance": (1, 5),
        "blast_radius":     (0, 10),
        "business_impact":  (0, 10),
        "fix_difficulty":   (1, 5),
        "confidence":       (0.0, 1.0),
    }
    WEIGHTS = {
        "exposure": 0.25,
        "exploitability": 0.20,
        "blast_radius": 0.15,
        "business_impact": 0.20,
        "asset_importance": 0.10,  # multiplied by *2 to rescale to 0-10
        "fix_difficulty":  0.10,   # inverted: (6 - fd) * 2
    }

    def score(self, raw: list[RawSubScores]) -> list[ScoredFinding]:
        composites: list[tuple[ScoredFinding, float]] = []
        for r in raw:
            clamped: list[str] = []
            exposure        = int(_clamp(r.exposure,         0, 10, "exposure",         clamped))
            exploitability  = int(_clamp(r.exploitability,   0, 10, "exploitability",   clamped))
            asset_imp       = int(_clamp(r.asset_importance, 1,  5, "asset_importance", clamped))
            blast_radius    = int(_clamp(r.blast_radius,     0, 10, "blast_radius",     clamped))
            business_impact = int(_clamp(r.business_impact,  0, 10, "business_impact",  clamped))
            fix_difficulty  = int(_clamp(r.fix_difficulty,   1,  5, "fix_difficulty",   clamped))
            confidence      = float(_clamp(r.confidence,    0.0, 1.0, "confidence",     clamped))

            weighted = (
                exposure        * self.WEIGHTS["exposure"]
                + exploitability  * self.WEIGHTS["exploitability"]
                + blast_radius    * self.WEIGHTS["blast_radius"]
                + business_impact * self.WEIGHTS["business_impact"]
                + (asset_imp * 2) * self.WEIGHTS["asset_importance"]
                + ((6 - fix_difficulty) * 2) * self.WEIGHTS["fix_difficulty"]
            )
            composite = round(weighted * confidence * 10, 2)

            composites.append((
                ScoredFinding(
                    finding_id=r.finding_id,
                    exposure=exposure,
                    exploitability=exploitability,
                    asset_importance=asset_imp,
                    blast_radius=blast_radius,
                    business_impact=business_impact,
                    fix_difficulty=fix_difficulty,
                    confidence=confidence,
                    composite=composite,
                    rank=0,  # set below
                    rationale=r.rationale,
                    clamped_fields=tuple(clamped),
                ),
                composite,
            ))

        # Stable ordering: composite DESC, then finding_id ASC for determinism.
        composites.sort(key=lambda p: (-p[1], str(p[0].finding_id)))

        return [
            ScoredFinding(
                **{**sf.__dict__, "rank": idx + 1}
            )
            for idx, (sf, _) in enumerate(composites)
        ]
