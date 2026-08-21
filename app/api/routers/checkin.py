import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import get_db
from app.db.models import Checkin, Jugador, Categoria, SesionDia
from app.api.schemas import CheckinCreate, CheckinResponse
from app.services.gamificacion import get_checkin_feedback
from app.services import alertas, bienestar, semaforo

router = APIRouter()
logger = logging.getLogger("api.checkin")


@router.post("/api/checkin", response_model=CheckinResponse, status_code=status.HTTP_201_CREATED)
async def create_checkin(payload: CheckinCreate, db: AsyncSession = Depends(get_db)):
    # Verify jugador exists and get categoria_id
    jugador = await db.get(Jugador, payload.jugador_id)
    if not jugador or not jugador.activo:
        raise HTTPException(404, "Jugador no encontrado")

    # Idempotency: if already checked in today, return existing record
    existing = await db.execute(
        select(Checkin).where(
            Checkin.jugador_id == payload.jugador_id,
            Checkin.fecha == payload.fecha,
        )
    )
    if record := existing.scalar_one_or_none():
        return CheckinResponse(
            id=record.id,
            jugador_id=record.jugador_id,
            fecha=record.fecha,
            asistencia=record.asistencia,
            feedback="Ya registraste tu check-in hoy ✅",
        )

    checkin = Checkin(
        jugador_id=payload.jugador_id,
        fecha=payload.fecha,
        asistencia=payload.asistencia,
        motivo_inasistencia=payload.motivo_inasistencia,
        sueno=payload.sueno,
        energia=payload.energia,
        animo=payload.animo,
        dolor_pre=payload.dolor_pre,
        alimentacion=payload.alimentacion,
        estres=payload.estres,
        hora_inicio_declarada=payload.hora_inicio_declarada,
        molestia_previa=payload.molestia_previa,
        molestia_zona=payload.molestia_zona,
        molestia_severidad=payload.molestia_severidad,
    )
    db.add(checkin)
    await db.flush()  # get checkin.id before commit

    # Atomically increment sesion_dia counter
    nuevo_total = await _upsert_sesion_checkin(db, jugador.categoria_id, payload.fecha)

    feedback = ""
    if payload.asistencia:
        feedback = await get_checkin_feedback(db, payload.jugador_id, jugador.categoria_id, payload.fecha)

    # Staff alerts & semáforo — must never break the player's registration
    try:
        if not payload.asistencia:
            await alertas.notificar_inasistencia(db, jugador, payload.motivo_inasistencia, payload.fecha)
        else:
            if payload.molestia_previa:
                # Only immediate WhatsApp for bloqueante (or legacy payloads without severity)
                if payload.molestia_severidad is None or payload.molestia_severidad == "bloqueante":
                    await alertas.notificar_molestia(db, jugador, payload.molestia_zona, "check-in", payload.fecha)
                await alertas.revisar_tendencia_molestia(db, jugador, payload.molestia_zona, payload.fecha)
            await bienestar.revisar_bienestar(db, jugador, payload.fecha)

        categoria = await db.get(Categoria, jugador.categoria_id)
        total_activos_result = await db.execute(
                select(func.count(Jugador.id)).where(
                    Jugador.categoria_id == categoria.id,
                    Jugador.activo == True,  # noqa: E712
                )
            )
        total_activos = total_activos_result.scalar_one()
        umbral = max(5, round(total_activos * 0.6))
        if nuevo_total >= umbral:
            await semaforo.enviar_semaforo(db, categoria, payload.fecha, total_activos=total_activos)
    except Exception:
        logger.exception("Error enviando alertas de check-in (jugador_id=%s)", jugador.id)

    await db.commit()
    await db.refresh(checkin)

    return CheckinResponse(
        id=checkin.id,
        jugador_id=checkin.jugador_id,
        fecha=checkin.fecha,
        asistencia=checkin.asistencia,
        feedback=feedback,
    )


async def _upsert_sesion_checkin(db: AsyncSession, categoria_id: int, fecha) -> int:
    """Atomically increment total_checkins and return the new count."""
    stmt = pg_insert(SesionDia).values(
        categoria_id=categoria_id,
        fecha=fecha,
        total_checkins=1,
    ).on_conflict_do_update(
        constraint="mp_uq_sesion_categoria_fecha",
        set_={"total_checkins": SesionDia.total_checkins + 1},
    ).returning(SesionDia.total_checkins)
    result = await db.execute(stmt)
    return result.scalar_one()
