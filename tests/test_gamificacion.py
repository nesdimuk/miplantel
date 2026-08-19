import pytest
from datetime import date, timedelta
from app.services.gamificacion import get_checkin_feedback, _get_streak

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.asyncio
async def test_feedback_primer_checkin(db, seed_data):
    jugador = seed_data["jugadores"][0]
    cat = seed_data["categoria"]
    today = date.today()

    # No previous checkins — should return position 1 message
    from app.db.models import Checkin
    checkin = Checkin(
        jugador_id=jugador.id,
        fecha=today,
        asistencia=True,
        sueno=5, energia=5, animo=5, dolor_pre=2,
    )
    db.add(checkin)
    await db.flush()

    feedback = await get_checkin_feedback(db, jugador.id, cat.id, today)
    assert "#1" in feedback or "1°" in feedback or "1" in feedback


@pytest.mark.asyncio
async def test_streak_zero_sin_historial(db, seed_data):
    jugador = seed_data["jugadores"][1]
    streak = await _get_streak(db, jugador.id, date.today())
    assert streak == 0


@pytest.mark.asyncio
async def test_streak_consecutivo(db, seed_data):
    jugador = seed_data["jugadores"][2]
    from app.db.models import Checkin

    today = date.today()
    for delta in range(1, 4):  # 3 consecutive days before today
        db.add(Checkin(
            jugador_id=jugador.id,
            fecha=today - timedelta(days=delta),
            asistencia=True,
            sueno=5, energia=5, animo=5, dolor_pre=2,
        ))
    await db.flush()

    streak = await _get_streak(db, jugador.id, today)
    assert streak == 3
