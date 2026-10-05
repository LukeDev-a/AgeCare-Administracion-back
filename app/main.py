"""AgeCare — API de la Consola de Administración (FastAPI + PostgreSQL)."""
from fastapi import APIRouter, FastAPI
import asyncio
from contextlib import asynccontextmanager, suppress
from app.invitation_mail import mail_worker


@asynccontextmanager
async def lifespan(app):
    worker = asyncio.create_task(mail_worker()) if get_settings().mail_worker_enabled else None
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker

from app.config import get_settings
from app.errors import RequestIdMiddleware, register_error_handlers
from app.routers import (auth, content, marketplace, metrics_commercial, metrics_features,
                         metrics_roles, moderation, ops, support, games_apps)
from app.routers import system as system_router, auditing
from fastapi.staticfiles import StaticFiles

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    lifespan=lifespan,
    title="AgeCare Admin API",
    version="1.0.0",
    description="Backend de la Consola de Administración de AgeCare · Wellq Co",
    docs_url="/api/v1/admin/docs",
    openapi_url="/api/v1/admin/openapi.json",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

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
api.include_router(metrics_commercial.router)
api.include_router(ops.router)
api.include_router(metrics_roles.router)
api.include_router(support.router)
api.include_router(metrics_features.router)
api.include_router(content.router)
api.include_router(marketplace.router)
api.include_router(moderation.router)
api.include_router(games_apps.router)
api.include_router(system_router.router)
api.include_router(auditing.router)
app.include_router(api)


@app.get("/health", tags=["Salud"])
async def health():
    return {"status": "ok", "service": get_settings().app_name}
