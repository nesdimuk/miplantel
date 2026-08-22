"""Post-training notification triggers.

enviar_primer_aviso  — fired when the 3rd check-in arrives (real-time, same DB session)
enviar_resumen_post  — fired 1h after the 3rd checkout (scheduler date-trigger job)
enviar_dashboard_dia — fired 3h after the 3rd checkout (scheduler date-trigger job)

The last two open their own DB sessions because they run as APScheduler jobs.
"""
import logging
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import AsyncSessionLocal
from app.db.models import Categoria, SesionDia
from app.services.alertas import enviar_a_staff

logger = logging.getLogger("services.notificaciones_post")


def _link(categoria_id: int, fecha: date) -> str:
    base = settings.base_url.rstrip("/") if settings.base_url else ""
    return f"{base}/r/{categoria_id}/{fecha.isoformat()}"


async def enviar_primer_aviso(
    db: AsyncSession,
    categoria: Categoria,
    fecha: date,
) -> bool:
    """Send the '3 check-ins' notice to staff. Fires once per session. Uses existing db session."""
    claimed = await db.execute(
        update(SesionDia)
        .where(
            SesionDia.categoria_id == categoria.id,
            SesionDia.fecha == fecha,
            SesionDia.primer_aviso_enviado == False,  # noqa: E712
        )
        .values(primer_aviso_enviado=True)
        .returning(SesionDia.id)
    )
    if claimed.scalar_one_or_none() is None:
        return False

    link = _link(categoria.id, fecha)
    await enviar_a_staff(
        db,
        club_id=categoria.club_id,
        tipo="primer_aviso_checkin",
        categoria_id=categoria.id,
        jugador_id=None,
        template="primer_aviso_checkin",
        variables=[categoria.nombre, link],
    )
    logger.info("Primer aviso enviado: %s %s", categoria.nombre, fecha)
    return True


async def _enviar_resumen_post_job(categoria_id: int, fecha_iso: str) -> None:
    """APScheduler job: resumen post-entrenamiento (pendientes + copy)."""
    fecha = date.fromisoformat(fecha_iso)
    async with AsyncSessionLocal() as db:
        try:
            categoria = await db.get(Categoria, categoria_id)
            if not categoria:
                return

            claimed = await db.execute(
                update(SesionDia)
                .where(
                    SesionDia.categoria_id == categoria_id,
                    SesionDia.fecha == fecha,
                    SesionDia.resumen_post_enviado == False,  # noqa: E712
                )
                .values(resumen_post_enviado=True)
                .returning(SesionDia.id)
            )
            if claimed.scalar_one_or_none() is None:
                return

            link = _link(categoria_id, fecha)
            await enviar_a_staff(
                db,
                club_id=categoria.club_id,
                tipo="resumen_post",
                categoria_id=categoria_id,
                jugador_id=None,
                template="resumen_post",
                variables=[categoria.nombre, link],
            )
            await db.commit()
            logger.info("Resumen post enviado: %s %s", categoria.nombre, fecha)
        except Exception:
            await db.rollback()
            logger.exception("Error en resumen post (categoria_id=%s)", categoria_id)


async def _enviar_dashboard_dia_job(categoria_id: int, fecha_iso: str) -> None:
    """APScheduler job: dashboard completo del día."""
    fecha = date.fromisoformat(fecha_iso)
    async with AsyncSessionLocal() as db:
        try:
            categoria = await db.get(Categoria, categoria_id)
            if not categoria:
                return

            claimed = await db.execute(
                update(SesionDia)
                .where(
                    SesionDia.categoria_id == categoria_id,
                    SesionDia.fecha == fecha,
                    SesionDia.dashboard_enviado == False,  # noqa: E712
                )
                .values(dashboard_enviado=True)
                .returning(SesionDia.id)
            )
            if claimed.scalar_one_or_none() is None:
                return

            link = _link(categoria_id, fecha)
            await enviar_a_staff(
                db,
                club_id=categoria.club_id,
                tipo="dashboard_dia",
                categoria_id=categoria_id,
                jugador_id=None,
                template="dashboard_dia",
                variables=[categoria.nombre, link],
            )
            await db.commit()
            logger.info("Dashboard día enviado: %s %s", categoria.nombre, fecha)
        except Exception:
            await db.rollback()
            logger.exception("Error en dashboard día (categoria_id=%s)", categoria_id)
