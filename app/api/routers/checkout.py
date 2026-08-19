import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import get_db
from app.db.models import Checkout, Checkin, Jugador, Categoria, SesionDia
from app.api.schemas import CheckoutCreate, CheckoutResponse
from app.services import alertas, bienestar

router = APIRouter()
logger = logging.getLogger("api.checkout")


@router.post("/api/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def create_checkout(payload: CheckoutCreate, db: AsyncSession = Depends(get_db)):
    jugador = await db.get(Jugador, payload.jugador_id)
    if not jugador or not jugador.activo:
        raise HTTPException(404, "Jugador no encontrado")

    # Must have checked in with asistencia=True today
    checkin = await db.execute(
        select(Checkin).where(
            Checkin.jugador_id == payload.jugador_id,
            Checkin.fecha == payload.fecha,
            Checkin.asistencia == True,  # noqa: E712
        )
    )
    if not checkin.scalar_one_or_none():
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

    # Derive duration from categoria config if not provided
    duracion_min = payload.duracion_min
    if duracion_min is None:
        categoria = await db.get(Categoria, jugador.categoria_id)
        duracion_min = _calcular_duracion(categoria.hora_inicio, categoria.hora_fin)

    carga = payload.rpe * duracion_min

    checkout = Checkout(
        jugador_id=payload.jugador_id,
        fecha=payload.fecha,
        rpe=payload.rpe,
        duracion_min=duracion_min,
        carga=carga,
        fisico_post=payload.fisico_post,
        rendimiento=payload.rendimiento,
        molestia_nueva=payload.molestia_nueva,
        molestia_zona=payload.molestia_zona,
        molestia_severidad=payload.molestia_severidad,
    )
    db.add(checkout)
    await db.flush()

    await _upsert_sesion_checkout(db, jugador.categoria_id, payload.fecha)

    # Immediate staff alerts — must never break the player's registration
    try:
        if payload.molestia_nueva:
            if payload.molestia_severidad is None or payload.molestia_severidad == "bloqueante":
                await alertas.notificar_molestia(db, jugador, payload.molestia_zona, "check-out", payload.fecha)
            await alertas.revisar_tendencia_molestia(db, jugador, payload.molestia_zona, payload.fecha)
        await bienestar.revisar_carga(db, jugador, payload.fecha)
    except Exception:
        logger.exception("Error enviando alertas de check-out (jugador_id=%s)", jugador.id)

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


async def _upsert_sesion_checkout(db: AsyncSession, categoria_id: int, fecha) -> None:
    stmt = pg_insert(SesionDia).values(
        categoria_id=categoria_id,
        fecha=fecha,
        total_checkouts=1,
    ).on_conflict_do_update(
        constraint="mp_uq_sesion_categoria_fecha",
        set_={"total_checkouts": SesionDia.total_checkouts + 1},
    )
    await db.execute(stmt)
