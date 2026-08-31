import logging
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Categoria, Checkin, Club, Jugador, SesionDia

logger = logging.getLogger("services.semaforo")

# Wellness score = (sueño + energía + ánimo + dolor invertido) / 4, escala 1-7
ESTADOS = [
    (5.0, "🟢 VERDE"),
    (3.5, "🟡 AMARILLO"),
    (0.0, "🔴 ROJO"),
]


def _hhmm_to_min(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def _min_to_hhmm(m: int) -> str:
    m = max(0, m)
    return f"{m // 60:02d}:{m % 60:02d}"


async def hora_disparo_semaforo(db: AsyncSession, cat: Categoria, fecha: date) -> str:
    """Return HH:MM when the scheduler should fire the semáforo.

    If ≥3 checkins have hora_inicio_declarada today, use the most common
    value minus 5 min. Otherwise fall back to cat.hora_inicio.
    """
    result = await db.execute(
        select(Checkin.hora_inicio_declarada)
        .join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(
            Jugador.categoria_id == cat.id,
            Checkin.fecha == fecha,
            Checkin.asistencia == True,  # noqa: E712
            Checkin.hora_inicio_declarada.isnot(None),
        )
    )
    valores = [r[0] for r in result.all()]
    if len(valores) >= 3:
        modo = Counter(valores).most_common(1)[0][0]
        return _min_to_hhmm(_hhmm_to_min(modo) - 5)
    if valores:  # 1-2 check-ins: hay señal pero insuficiente, esperar más
        return "23:59"
    return cat.hora_inicio  # sin check-ins: usar hora configurada como referencia


UMBRAL_ROJO_BIENESTAR = 3.5


def _bienestar_jugador(c: Checkin) -> Optional[float]:
    # Índice Hooper: sueño + energía + (8-dolor) + (8-estrés) → rango 1-7, mayor=mejor
    # Ánimo se registra pero no entra al score validado
    if any(getattr(c, f) is None for f in ("sueno", "energia", "dolor_pre", "estres")):
        return None
    return (c.sueno + c.energia + (8 - c.dolor_pre) + (8 - c.estres)) / 4


async def calcular_semaforo(db: AsyncSession, categoria_id: int, fecha: date) -> Optional[dict]:
    """Return checkin count and list of rojo players for today. None if no data."""
    result = await db.execute(
        select(Checkin, Jugador)
        .join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(
            Jugador.categoria_id == categoria_id,
            Checkin.fecha == fecha,
            Checkin.asistencia == True,  # noqa: E712
        )
    )
    rows = result.all()
    if not rows:
        return None

    rojos = []
    for checkin, jugador in rows:
        b = _bienestar_jugador(checkin)
        if b is not None and b < UMBRAL_ROJO_BIENESTAR:
            rojos.append({
                "nombre": f"{jugador.nombre} {jugador.apellido}",
                "sueno": checkin.sueno,
                "energia": checkin.energia,
                "animo": checkin.animo,
                "dolor": checkin.dolor_pre,
                "bienestar": round(b, 2),
            })

    return {"checkins": len(rows), "rojos": rojos}


async def enviar_semaforo(
    db: AsyncSession,
    categoria: Categoria,
    fecha: date,
    forzado: bool = False,
    total_activos: int = 0,
) -> bool:
    """Send pre-training wellness report to staff, exactly once per day.

    Lists players in rojo; if none, sends a positive message.
    Returns True if this call performed the send.
    """
    stats = await calcular_semaforo(db, categoria.id, fecha)
    if stats is None:
        logger.debug("Semáforo %s %s: sin datos, se omite", categoria.nombre, fecha)
        return False

    if not forzado and total_activos > 0:
        umbral = max(5, round(total_activos * 0.6))
        if stats["checkins"] < umbral:
            return False

    if not await _claim_semaforo(db, categoria.id, fecha):
        return False

    if stats["rojos"]:
        lineas = "\n".join(
            f"• {j['nombre']} — sueño {j['sueno']}, energía {j['energia']}, ánimo {j['animo']}, dolor {j['dolor']}"
            for j in stats["rojos"]
        )
        bloque = f"🔴 Jugadores que vienen bajo hoy:\n{lineas}"
    else:
        bloque = "💪 Todo el grupo viene bien hoy"

    total_str = str(total_activos) if total_activos else "?"
    link = (
        f"{settings.base_url.rstrip('/')}/r/{categoria.id}/{fecha.isoformat()}"
        if settings.base_url else f"/r/{categoria.id}/{fecha.isoformat()}"
    )
    # Semáforo no envía mensaje Telegram — el profe lo ve en la página
    # Programar jobs de post-entreno como fallback si no llegan 3 checkouts
    _schedule_fallback_jobs(categoria, fecha)
    logger.info("Semáforo calculado: %s %s — %d rojos (sin mensaje TG)", categoria.nombre, fecha, len(stats["rojos"]))
    return True


def _schedule_fallback_jobs(categoria: Categoria, fecha: date) -> None:
    """Schedule post-training messages at hora_inicio+2h and +4h as fallback."""
    try:
        from app.scheduler.jobs import scheduler
        from app.services.notificaciones_post import _enviar_resumen_post_job, _enviar_dashboard_dia_job

        tz = ZoneInfo("America/Santiago")
        h, m = map(int, categoria.hora_inicio.split(":"))
        inicio = datetime(fecha.year, fecha.month, fecha.day, h, m, tzinfo=tz)
        fecha_iso = fecha.isoformat()

        scheduler.add_job(
            _enviar_resumen_post_job,
            trigger="date",
            run_date=inicio + timedelta(hours=2),
            args=[categoria.id, fecha_iso],
            id=f"resumen_post_{categoria.id}_{fecha_iso}",
            replace_existing=False,
            misfire_grace_time=3600,
        )
        scheduler.add_job(
            _enviar_dashboard_dia_job,
            trigger="date",
            run_date=inicio + timedelta(hours=4),
            args=[categoria.id, fecha_iso],
            id=f"dashboard_dia_{categoria.id}_{fecha_iso}",
            replace_existing=False,
            misfire_grace_time=3600,
        )
        logger.info(
            "Fallback jobs programados: %s %s (+2h resumen, +4h dashboard desde hora_inicio)",
            categoria.nombre, fecha,
        )
    except Exception:
        logger.exception("Error programando fallback jobs para %s %s", categoria.nombre, fecha)


async def _claim_semaforo(db: AsyncSession, categoria_id: int, fecha: date) -> bool:
    """Atomically claim the daily send. Ensures the sesion row exists first."""
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
            SesionDia.semaforo_enviado == False,  # noqa: E712
        )
        .values(semaforo_enviado=True)
        .returning(SesionDia.id)
    )
    return result.scalar_one_or_none() is not None
