from datetime import date, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Checkin, Jugador


async def get_checkin_feedback(
    session: AsyncSession,
    jugador_id: int,
    categoria_id: int,
    fecha: date,
) -> str:
    """Return gamified feedback string shown on screen after a successful check-in."""

    # Position of this player in today's check-ins for the category
    result = await session.execute(
        select(func.count())
        .select_from(Checkin)
        .join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(
            Checkin.fecha == fecha,
            Checkin.asistencia == True,  # noqa: E712
            Jugador.categoria_id == categoria_id,
        )
    )
    position = result.scalar_one()

    # Consecutive days streak for this player
    streak = await _get_streak(session, jugador_id, fecha)

    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(position, "⚡")

    lines = []
    if position <= 3:
        lines.append(f"{medal} ¡Eres el #{position} del día en registrar!")
    else:
        lines.append(f"✅ Check-in registrado (#{position} del día)")

    if streak >= 7:
        lines.append(f"🔥 ¡Racha de {streak} días seguidos! ¡Imparable!")
    elif streak >= 3:
        lines.append(f"⚡ {streak} días consecutivos — ¡sigue así!")

    return " ".join(lines)


async def _get_streak(session: AsyncSession, jugador_id: int, today: date) -> int:
    """Count consecutive days with asistencia=True going back from yesterday."""
    streak = 0
    day = today - timedelta(days=1)
    for _ in range(30):  # cap at 30 to avoid long loops
        result = await session.execute(
            select(Checkin).where(
                Checkin.jugador_id == jugador_id,
                Checkin.fecha == day,
                Checkin.asistencia == True,  # noqa: E712
            )
        )
        if result.scalar_one_or_none() is None:
            break
        streak += 1
        day -= timedelta(days=1)
    return streak
