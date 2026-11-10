"""AgeCare — API de la Consola de Administración (FastAPI + PostgreSQL)."""
from fastapi import APIRouter, FastAPI
import asyncio
from contextlib import asynccontextmanager, suppress
from app.invitation_mail import mail_worker


@asynccontextmanager
async def lifespan(app):
    worker = asyncio.create_task(mail_worker()) if get_settings().mail_worker_enabled else None
    from app.incident_mail import incident_mail_worker
    incident_worker = asyncio.create_task(incident_mail_worker()) if get_settings().mail_worker_enabled else None
    from app.password_reset import password_reset_worker
    reset_worker = asyncio.create_task(password_reset_worker()) if get_settings().mail_worker_enabled else None
    from app.content_pipeline import content_worker
    editorial_worker = asyncio.create_task(content_worker()) if get_settings().content_worker_enabled else None
    from app.commercial_analytics import commercial_worker
    metrics_worker = asyncio.create_task(commercial_worker()) if get_settings().commercial_worker_enabled else None
    try:
        yield
    finally:
        if reset_worker:
            reset_worker.cancel()
            with suppress(asyncio.CancelledError):
                await reset_worker
        if incident_worker:
            incident_worker.cancel()
            with suppress(asyncio.CancelledError):
                await incident_worker
        if metrics_worker:
            metrics_worker.cancel()
            with suppress(asyncio.CancelledError):
                await metrics_worker
        if editorial_worker:
            editorial_worker.cancel()
            with suppress(asyncio.CancelledError):
                await editorial_worker
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker

from app.config import get_settings
from app.errors import RequestIdMiddleware, register_error_handlers
from app.routers import (auth, content, marketplace, metrics_commercial, metrics_features,
                         metrics_roles, moderation, ops, support, games_apps)
from app.routers import system as system_router, auditing
from app.routers import end_users
from app.game_static import GameStaticFiles

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    lifespan=lifespan,
    title="AgeCare Admin API",
    version="1.0.0",
    description="Backend de la Consola de Administración de AgeCare · Wellq Co",
    docs_url="/api/v1/admin/docs",
    openapi_url="/api/v1/admin/openapi.json",
)

app.mount("/static", GameStaticFiles(directory="app/static"), name="static")

origenes_permitidos = get_settings().allows_origins.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins= origenes_permitidos, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

api = APIRouter(prefix="/api/v1/admin")
api.include_router(auth.router)
from app.routers import account_access
api.include_router(account_access.router)
from app.routers import password_reset
api.include_router(password_reset.router)
api.include_router(metrics_commercial.router)
api.include_router(ops.router)
api.include_router(metrics_roles.router)
api.include_router(support.router)
api.include_router(metrics_features.router)
api.include_router(content.router)
from app.routers import content_candidates
api.include_router(content_candidates.router)
api.include_router(marketplace.router)
api.include_router(moderation.router)
api.include_router(games_apps.router)
api.include_router(system_router.router)
api.include_router(auditing.router)
api.include_router(end_users.router)
app.include_router(api)


@app.get("/health", tags=["Salud"])
async def health():
    return {"status": "ok", "service": get_settings().app_name}
