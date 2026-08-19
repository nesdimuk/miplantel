import logging
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Categoria, Checkin, Checkout, Jugador, SesionDia
from app.services.alertas import enviar_a_staff

logger = logging.getLogger("services.resumen")


async def generar_resumen(db: AsyncSession, categoria: Categoria, fecha: date) -> dict:
    """Aggregate the day's activity for one category."""
    total_jugadores = (await db.execute(
        select(func.count(Jugador.id)).where(
            Jugador.categoria_id == categoria.id,
            Jugador.activo == True,  # noqa: E712
        )
    )).scalar_one()

    checkins = (await db.execute(
        select(Checkin, Jugador)
        .join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria.id, Checkin.fecha == fecha)
    )).all()

    checkouts = (await db.execute(
        select(Checkout, Jugador)
        .join(Jugador, Checkout.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria.id, Checkout.fecha == fecha)
    )).all()

    asistieron = [(c, j) for c, j in checkins if c.asistencia]
    inasistencias = [
        f"{j.nombre} {j.apellido} ({c.motivo_inasistencia or 'sin motivo'})"
        for c, j in checkins if not c.asistencia
    ]
    def _sev(sev): return f", {sev}" if sev else ""

    molestias = [
        f"{j.nombre} {j.apellido} ({c.molestia_zona or 'zona no indicada'}{_sev(c.molestia_severidad)}, ci)"
        for c, j in asistieron if c.molestia_previa
    ] + [
        f"{j.nombre} {j.apellido} ({c.molestia_zona or 'zona no indicada'}{_sev(c.molestia_severidad)}, co)"
        for c, j in checkouts if c.molestia_nueva
    ]

    ids_con_checkout = {c.jugador_id for c, _ in checkouts}
    sin_checkout = [
        f"{j.nombre} {j.apellido}"
        for c, j in asistieron if c.jugador_id not in ids_con_checkout
    ]

    rpes = [c.rpe for c, _ in checkouts]
    cargas = [c.carga for c, _ in checkouts]

    return {
        "total_jugadores": total_jugadores,
        "asistieron": len(asistieron),
        "inasistencias": inasistencias,
        "molestias": molestias,
        "sin_checkout": sin_checkout,
        "rpe_promedio": round(sum(rpes) / len(rpes), 1) if rpes else None,
        "carga_promedio": round(sum(cargas) / len(cargas)) if cargas else None,
    }


async def enviar_resumen(db: AsyncSession, categoria: Categoria, fecha: date) -> bool:
    """Send the daily summary to staff, exactly once per day. True if sent by this call."""
    if not await _claim_resumen(db, categoria.id, fecha):
        return False

    r = await generar_resumen(db, categoria, fecha)
    # WhatsApp template parameters must not contain newlines → join lists with "; "
    variables = [
        categoria.nombre,
        fecha.strftime("%d/%m/%Y"),
        f"{r['asistieron']}/{r['total_jugadores']}",
        "; ".join(r["inasistencias"]) or "Ninguna",
        "; ".join(r["molestias"]) or "Ninguna",
        "; ".join(r["sin_checkout"]) or "Ninguno",
        str(r["rpe_promedio"]) if r["rpe_promedio"] is not None else "—",
        str(r["carga_promedio"]) if r["carga_promedio"] is not None else "—",
    ]
    await enviar_a_staff(
        db,
        club_id=categoria.club_id,
        tipo="resumen",
        categoria_id=categoria.id,
        jugador_id=None,
        template="resumen_diario",
        variables=variables,
        canal="resumen",
    )
    logger.info("Resumen enviado: %s %s", categoria.nombre, fecha)
    return True


async def _claim_resumen(db: AsyncSession, categoria_id: int, fecha: date) -> bool:
    await db.execute(
        pg_insert(SesionDia)
        .values(categoria_id=categoria_id, fecha=fecha)
        .on_conflict_do_nothing(constraint="mp_uq_sesion_categoria_fecha")
    )
    result = await db.execute(
        update(SesionDia)
        .where(
            SesionDia.categoria_id == categoria_id,
            SesionDia.fecha == fecha,
            SesionDia.resumen_enviado == False,  # noqa: E712
        )
        .values(resumen_enviado=True)
        .returning(SesionDia.id)
    )
    return result.scalar_one_or_none() is not None
