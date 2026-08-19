"""Scheduled jobs: forced semáforo at training start, daily summary at hora_resumen.

A single tick runs every minute and evaluates all active categories in their
club's timezone. Sends are idempotent (claimed via sesiones_dia flags), so the
`>=` time comparison makes the system self-healing: if the process was down at
the exact minute, the next tick sends it late instead of never.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db.engine import AsyncSessionLocal
from app.db.models import Categoria
from app.services import recordatorios as recordatorios_svc
from app.services import resumen as resumen_svc
from app.services import semaforo as semaforo_svc

logger = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler()


async def tick() -> None:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Categoria)
                .options(joinedload(Categoria.club))
                .where(Categoria.activo == True)  # noqa: E712
            )
            categorias = result.scalars().all()

            for cat in categorias:
                if not cat.club.activo:
                    continue
                ahora = datetime.now(ZoneInfo(cat.club.timezone))
                if ahora.weekday() not in cat.dias_entrenamiento:
                    continue
                hhmm = ahora.strftime("%H:%M")
                hoy = ahora.date()

                await recordatorios_svc.evaluar_recordatorios(db, cat, hoy, hhmm)
                if hhmm >= cat.hora_inicio:
                    await semaforo_svc.enviar_semaforo(db, cat, hoy, forzado=True)
                if hhmm >= cat.hora_resumen:
                    await resumen_svc.enviar_resumen(db, cat, hoy)

            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Error en tick del scheduler")


def start_scheduler() -> None:
    scheduler.add_job(tick, "interval", minutes=1, id="tick", max_instances=1, coalesce=True)
    scheduler.start()
    logger.info("Scheduler iniciado (tick cada 1 min)")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
