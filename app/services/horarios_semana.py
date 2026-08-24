"""Sunday schedule confirmation: send current schedule to each coach, ask them to confirm or update."""
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import AsyncSessionLocal
from app.db.models import Categoria, Club, Staff
from app.services.horarios_bot import enviar_texto_whatsapp

logger = logging.getLogger("services.horarios_semana")

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _formato_horario(cat: Categoria) -> str:
    dias_str = " · ".join(DIAS[d] for d in sorted(cat.dias_entrenamiento))
    return f"*{cat.nombre}*: {dias_str} a las {cat.hora_inicio}"


async def marcar_horario_confirmado(db: AsyncSession, categoria_ids: list[int]) -> None:
    """Mark categories as having a confirmed schedule (called after coach confirms or updates)."""
    if not categoria_ids:
        return
    await db.execute(
        update(Categoria)
        .where(Categoria.id.in_(categoria_ids))
        .values(horario_confirmado=True)
    )


async def enviar_confirmacion_horarios_job() -> None:
    """APScheduler job: send Sunday schedule message to all active DT coaches."""
    async with AsyncSessionLocal() as db:
        try:
            clubs = (await db.execute(
                select(Club).where(Club.activo == True)  # noqa: E712
            )).scalars().all()

            for club in clubs:
                categorias = (await db.execute(
                    select(Categoria).where(
                        Categoria.club_id == club.id,
                        Categoria.activo == True,  # noqa: E712
                    )
                )).scalars().all()

                cat_by_id = {c.id: c for c in categorias}

                coaches = (await db.execute(
                    select(Staff).where(
                        Staff.club_id == club.id,
                        Staff.activo == True,  # noqa: E712
                        Staff.rol == "DT",
                        Staff.es_coordinador == False,  # noqa: E712
                    )
                )).scalars().all()

                for coach in coaches:
                    mis_cats = (
                        [cat_by_id[cid] for cid in coach.categoria_ids if cid in cat_by_id]
                        if coach.categoria_ids
                        else list(categorias)
                    )
                    if not mis_cats:
                        continue

                    primera_vez = any(not c.horario_confirmado for c in mis_cats)
                    cats_nombres = " y ".join(sorted(c.nombre for c in mis_cats))

                    if primera_vez:
                        mensaje = (
                            f"👋 Hola, soy el asistente de *{club.nombre}*.\n\n"
                            f"Para configurar los avisos de esta semana, "
                            f"dime los horarios de entrenamiento de *{cats_nombres}*.\n\n"
                            f"Ejemplo:\n"
                            f"_Sub-13 entrena lunes, miércoles y viernes a las 15:30_\n"
                            f"_Sub-14 entrena martes y jueves a las 16:00_"
                        )
                    else:
                        horarios = "\n".join(_formato_horario(c) for c in sorted(mis_cats, key=lambda c: c.nombre))
                        mensaje = (
                            f"📅 *{club.nombre} · Horarios esta semana*\n\n"
                            f"{horarios}\n\n"
                            f"¿Se mantienen estos horarios?\n"
                            f"✅ Responde *si* para confirmar\n"
                            f"✏️ O escríbeme el nuevo horario"
                        )

                    await enviar_texto_whatsapp(coach.telefono_whatsapp, mensaje)
                    logger.info(
                        "Confirmación horarios enviada a %s (%s) — %s",
                        coach.nombre, club.nombre,
                        "primera vez" if primera_vez else "confirmación",
                    )

            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Error en enviar_confirmacion_horarios_job")
