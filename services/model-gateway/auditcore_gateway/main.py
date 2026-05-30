from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import settings
from .cost import CostBook
from .gateway import Gateway
from .routing import Router
from .types import CompleteRequest, ModelResponse, TaskKind

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("auditcore.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    router = Router.from_yaml(settings.routing_config)
    pricing_path = settings.routing_config.parent / "pricing.yaml"
    app.state.gateway = Gateway(router=router, costs=CostBook.from_yaml(pricing_path))
    log.info("model gateway ready (routing=%s)", settings.routing_config)
    yield


app = FastAPI(title="AuditCore Model Gateway", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


class ResolveRequest(BaseModel):
    task_kind: TaskKind
    budget_hint: str = "normal"
    privacy: str = "standard"


@app.post("/v1/resolve")
def resolve(body: ResolveRequest) -> dict:
    """Resolve a route without making a model call — useful for inspection/UI."""
    router: Router = app.state.gateway.router
    decision = router.resolve(body.task_kind, body.budget_hint, body.privacy)  # type: ignore[arg-type]
    return {
        "primary":   {"provider": decision.primary[0],   "model": decision.primary[1]},
        "secondary": ({"provider": decision.secondary[0], "model": decision.secondary[1]}
                       if decision.secondary else None),
        "tertiary":  ({"provider": decision.tertiary[0],  "model": decision.tertiary[1]}
                       if decision.tertiary else None),
        "critic_loop": decision.critic_loop,
    }


@app.post("/v1/complete", response_model=ModelResponse)
async def complete(req: CompleteRequest) -> ModelResponse:
    gateway: Gateway = app.state.gateway
    try:
        return await gateway.complete(req)
    except Exception as e:
        log.exception("gateway.complete failed")
        raise HTTPException(status_code=502, detail=str(e)) from e
