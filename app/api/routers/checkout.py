import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import get_db
from app.db.models import Checkout, Checkin, Jugador, Categoria, SesionDia
from app.api.schemas import CheckoutCreate, CheckoutResponse
from app.services.notificaciones_post import _enviar_resumen_post_job, _enviar_dashboard_dia_job
from app.scheduler.jobs import scheduler

router = APIRouter()
logger = logging.getLogger("api.checkout")


@router.post("/api/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def create_checkout(payload: CheckoutCreate, db: AsyncSession = Depends(get_db)):
    jugador = await db.get(Jugador, payload.jugador_id)
    if not jugador or not jugador.activo:
        raise HTTPException(404, "Jugador no encontrado")

    # Must have checked in with asistencia=True today
    checkin_result = await db.execute(
        select(Checkin).where(
            Checkin.jugador_id == payload.jugador_id,
            Checkin.fecha == payload.fecha,
            Checkin.asistencia == True,  # noqa: E712
        )
    )
    checkin_hoy = checkin_result.scalar_one_or_none()
    if not checkin_hoy:
        raise HTTPException(400, "El jugador no tiene check-in de asistencia para esta fecha")

    # Idempotency
    existing = await db.execute(
        select(Checkout).where(
            Checkout.jugador_id == payload.jugador_id,
            Checkout.fecha == payload.fecha,
        )
    )
    if record := existing.scalar_one_or_none():
        return CheckoutResponse(
            id=record.id,
            jugador_id=record.jugador_id,
            fecha=record.fecha,
            rpe=record.rpe,
            duracion_min=record.duracion_min,
            carga=record.carga,
        )

    # Derive duration: hora_termino (individual) > duracion_min explícito > config categoría
    if payload.hora_termino:
        hora_inicio_ref = checkin_hoy.hora_inicio_declarada
        if not hora_inicio_ref:
            categoria = await db.get(Categoria, jugador.categoria_id)
            hora_inicio_ref = categoria.hora_inicio
        duracion_min = _calcular_duracion(hora_inicio_ref, payload.hora_termino)
    elif payload.duracion_min is not None:
        duracion_min = payload.duracion_min
    else:
        categoria = await db.get(Categoria, jugador.categoria_id)
        duracion_min = _calcular_duracion(categoria.hora_inicio, categoria.hora_fin)

    carga = payload.rpe * duracion_min

    checkout = Checkout(
        jugador_id=payload.jugador_id,
        fecha=payload.fecha,
        rpe=payload.rpe,
        duracion_min=duracion_min,
        carga=carga,
        hora_termino=payload.hora_termino,
        fisico_post=payload.fisico_post,
        rendimiento=payload.rendimiento,
        molestia_nueva=payload.molestia_nueva,
        molestia_zona=payload.molestia_zona,
        molestia_severidad=payload.molestia_severidad,
    )
    db.add(checkout)
    await db.flush()

    nuevo_total_co = await _upsert_sesion_checkout(db, jugador.categoria_id, payload.fecha)

    # Trigger 4+5: 3rd checkout → schedule resumen_post (+1h) and dashboard (+3h)
    try:
        if nuevo_total_co == 3:
            await _schedule_post_training(db, jugador.categoria_id, payload.fecha)
    except Exception:
        logger.exception("Error programando post-training (jugador_id=%s)", jugador.id)

    await db.commit()
    await db.refresh(checkout)

    return CheckoutResponse(
        id=checkout.id,
        jugador_id=checkout.jugador_id,
        fecha=checkout.fecha,
        rpe=checkout.rpe,
        duracion_min=checkout.duracion_min,
        carga=checkout.carga,
    )


def _calcular_duracion(hora_inicio: str, hora_fin: str) -> int:
    """Return training duration in minutes from HH:MM strings."""
    hi = int(hora_inicio[:2]) * 60 + int(hora_inicio[3:])
    hf = int(hora_fin[:2]) * 60 + int(hora_fin[3:])
    return max(hf - hi, 1)


async def _upsert_sesion_checkout(db: AsyncSession, categoria_id: int, fecha) -> int:
    """Atomically increment total_checkouts and return the new count."""
    stmt = pg_insert(SesionDia).values(
        categoria_id=categoria_id,
        fecha=fecha,
        total_checkouts=1,
    ).on_conflict_do_update(
        constraint="mp_uq_sesion_categoria_fecha",
        set_={"total_checkouts": SesionDia.total_checkouts + 1},
    ).returning(SesionDia.total_checkouts)
    result = await db.execute(stmt)
    return result.scalar_one()


async def _schedule_post_training(db: AsyncSession, categoria_id: int, fecha) -> None:
    """Record tercer_checkout_at and schedule post-training notification jobs."""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(SesionDia)
        .where(
            SesionDia.categoria_id == categoria_id,
            SesionDia.fecha == fecha,
            SesionDia.tercer_checkout_at.is_(None),
        )
        .values(tercer_checkout_at=now)
    )

    fecha_iso = fecha.isoformat() if not isinstance(fecha, str) else fecha
    run_resumen = now + timedelta(hours=1)
    run_dashboard = now + timedelta(hours=3)

    scheduler.add_job(
        _enviar_resumen_post_job,
        trigger="date",
        run_date=run_resumen,
        args=[categoria_id, fecha_iso],
        id=f"resumen_post_{categoria_id}_{fecha_iso}",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _enviar_dashboard_dia_job,
        trigger="date",
        run_date=run_dashboard,
        args=[categoria_id, fecha_iso],
        id=f"dashboard_dia_{categoria_id}_{fecha_iso}",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(
        "Post-training jobs scheduled for categoria_id=%s fecha=%s (+1h resumen, +3h dashboard)",
        categoria_id, fecha_iso,
    )
