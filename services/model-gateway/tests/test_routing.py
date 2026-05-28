from pathlib import Path

import pytest

from auditcore_gateway.routing import Router, RoutingError
from auditcore_gateway.types import TaskKind

ROUTING = Path(__file__).resolve().parents[1] / "routing.yaml"


@pytest.fixture(scope="module")
def router() -> Router:
    return Router.from_yaml(ROUTING)


def test_default_reason_normal(router: Router) -> None:
    d = router.resolve(TaskKind.REASON, "normal", "standard")
    assert d.primary[0] == "anthropic"


def test_air_gapped_only_uses_local(router: Router) -> None:
    for task in TaskKind:
        d = router.resolve(task, "normal", "air_gapped")
        assert d.primary[0] == "local", f"{task} should be local in air_gapped"
        assert d.secondary is None and d.tertiary is None


def test_sensitive_strips_denied_providers(router: Router) -> None:
    # SUMMARIZE budget=low has google in the tertiary slot — should be stripped.
    d = router.resolve(TaskKind.SUMMARIZE, "low", "sensitive")
    for slot in (d.primary, d.secondary, d.tertiary):
        if slot is not None:
            assert slot[0] != "google"


def test_unknown_combination_raises() -> None:
    # Empty table to force a miss.
    r = Router({"defaults": {}, "privacy_overrides": {}})
    with pytest.raises((RoutingError, KeyError)):
        r.resolve(TaskKind.REASON, "normal", "standard")
