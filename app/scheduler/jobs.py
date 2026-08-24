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
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.db.engine import AsyncSessionLocal
from app.db.models import Categoria, Jugador, SesionDia
from app.services import recordatorios as recordatorios_svc
from app.services import resumen as resumen_svc
from app.services import semaforo as semaforo_svc
from app.services.horarios_semana import enviar_confirmacion_horarios_job

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
                hora_disparo = await semaforo_svc.hora_disparo_semaforo(db, cat, hoy)
                # Si el primer aviso ya salió, dar 10 min de gracia antes del semáforo
                sesion_res = await db.execute(
                    select(SesionDia).where(SesionDia.categoria_id == cat.id, SesionDia.fecha == hoy)
                )
                sesion = sesion_res.scalar_one_or_none()
                if sesion and sesion.primer_aviso_enviado and not sesion.semaforo_enviado:
                    h, m = int(hora_disparo[:2]), int(hora_disparo[3:])
                    total = h * 60 + m + 10
                    hora_disparo = f"{total // 60:02d}:{total % 60:02d}"
                if hhmm >= hora_disparo:
                    total_activos = (await db.execute(
                        select(func.count(Jugador.id)).where(
                            Jugador.categoria_id == cat.id,
                            Jugador.activo == True,  # noqa: E712
                        )
                    )).scalar_one()
                    await semaforo_svc.enviar_semaforo(db, cat, hoy, forzado=True, total_activos=total_activos)
                if hhmm >= cat.hora_resumen:
                    await resumen_svc.enviar_resumen(db, cat, hoy)

            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Error en tick del scheduler")


def start_scheduler() -> None:
    scheduler.add_job(tick, "interval", minutes=1, id="tick", max_instances=1, coalesce=True)
    # Sunday at 10:00 local time: ask coaches to confirm the week's schedule
    scheduler.add_job(
        enviar_confirmacion_horarios_job,
        "cron",
        day_of_week="sun",
        hour=18,
        minute=0,
        id="confirmacion_horarios",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado (tick cada 1 min, confirmación horarios domingos 18:00)")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
