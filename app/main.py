import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.routers import admin, checkin, checkout, dashboards, forms, registro, webhooks
from app.config import settings
from app.scheduler.jobs import start_scheduler, stop_scheduler

APP_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO if settings.environment == "development" else logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment != "test":
        start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Mi Plantel",
    description="Sistema de monitoreo de bienestar y carga deportiva",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(checkin.router)
app.include_router(checkout.router)
app.include_router(forms.router)
app.include_router(webhooks.router)
app.include_router(admin.login_router)
app.include_router(admin.router)
app.include_router(dashboards.router)
app.include_router(registro.router)

app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
