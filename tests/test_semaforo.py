import pytest
from datetime import date

from httpx import AsyncClient

from app.db.models import Checkin
from app.messaging import get_provider
from app.services.semaforo import calcular_semaforo, enviar_semaforo

pytestmark = pytest.mark.asyncio(loop_scope="session")

HOY = date.today()


def _checkin(jugador_id, sueno, energia, animo, dolor, fecha=HOY):
    return Checkin(
        jugador_id=jugador_id, fecha=fecha, asistencia=True,
        sueno=sueno, energia=energia, animo=animo, dolor_pre=dolor,
    )


async def test_calculo_verde(db, seed_data):
    j = seed_data["jugadores"]
    db.add_all([_checkin(j[0].id, 6, 6, 6, 1), _checkin(j[1].id, 7, 6, 7, 1)])
    await db.flush()

    stats = await calcular_semaforo(db, seed_data["categoria"].id, HOY)
    assert stats["checkins"] == 2
    assert stats["sueno"] == 6.5
    assert stats["dolor"] == 1.0
    assert "VERDE" in stats["estado"]


async def test_calculo_rojo(db, seed_data):
    j = seed_data["jugadores"]
    db.add_all([_checkin(j[0].id, 2, 2, 2, 6), _checkin(j[1].id, 1, 2, 1, 7)])
    await db.flush()

    stats = await calcular_semaforo(db, seed_data["categoria"].id, HOY)
    assert "ROJO" in stats["estado"]


async def test_sin_datos_devuelve_none(db, seed_data):
    stats = await calcular_semaforo(db, seed_data["categoria"].id, HOY)
    assert stats is None


async def test_semaforo_se_dispara_al_llegar_al_umbral(client: AsyncClient, db, seed_data):
    """min_checkins_semaforo=2 in the fixture: 2nd check-in triggers, 3rd doesn't resend."""
    provider = get_provider()
    j = seed_data["jugadores"]

    for i, jugador in enumerate(j):
        await client.post("/api/checkin", json={
            "jugador_id": jugador.id, "fecha": HOY.isoformat(), "asistencia": True,
            "sueno": 6, "energia": 6, "animo": 6, "dolor_pre": 1,
        })
        semaforos = [m for m in provider.sent if m["template"] == "semaforo_diario"]
        assert len(semaforos) == (1 if i >= 1 else 0), f"tras checkin {i + 1}"

    semaforo_msg = next(m for m in provider.sent if m["template"] == "semaforo_diario")
    assert "VERDE" in semaforo_msg["preview"]
    assert "Sub-13" in semaforo_msg["preview"]


async def test_semaforo_forzado_ignora_umbral(client: AsyncClient, db, seed_data):
    provider = get_provider()
    jugador = seed_data["jugadores"][0]
    await client.post("/api/checkin", json={
        "jugador_id": jugador.id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 4, "energia": 4, "animo": 4, "dolor_pre": 4,
    })
    assert not any(m["template"] == "semaforo_diario" for m in provider.sent)  # 1 < umbral 2

    enviado = await enviar_semaforo(db, seed_data["categoria"], HOY, forzado=True)
    assert enviado is True
    assert any(m["template"] == "semaforo_diario" for m in provider.sent)

    # Second forced send is a no-op (already claimed)
    enviado_2 = await enviar_semaforo(db, seed_data["categoria"], HOY, forzado=True)
    assert enviado_2 is False
    semaforos = [m for m in provider.sent if m["template"] == "semaforo_diario"]
    assert len(semaforos) == 1


async def test_semaforo_forzado_sin_datos_no_envia(db, seed_data):
    enviado = await enviar_semaforo(db, seed_data["categoria"], HOY, forzado=True)
    assert enviado is False
    assert not any(m["template"] == "semaforo_diario" for m in get_provider().sent)
