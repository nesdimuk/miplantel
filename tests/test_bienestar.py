import pytest
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import AlertaLog, Checkin, Checkout
from app.messaging import get_provider
from app.services.bienestar import revisar_bienestar
from app.services.carga import calcular_acwr, carga_aguda

pytestmark = pytest.mark.asyncio(loop_scope="session")

HOY = date.today()


async def test_alerta_bienestar_sueno_bajo(client: AsyncClient, db, seed_data):
    jugador = seed_data["jugadores"][0]
    # Two past check-ins with critically low sleep
    for dias in (1, 2):
        db.add(Checkin(
            jugador_id=jugador.id, fecha=HOY - timedelta(days=dias), asistencia=True,
            sueno=1, energia=4, animo=5, dolor_pre=2,
        ))
    await db.commit()

    # Third one (today) via API → avg sueño = (1+1+2)/3 ≈ 1.3 ≤ 2 → alert
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 2, "energia": 4, "animo": 5, "dolor_pre": 2,
    })
    assert resp.status_code == 201

    provider = get_provider()
    bienestar_msgs = [m for m in provider.sent if m["template"] == "alerta_bienestar"]
    assert len(bienestar_msgs) == 1
    assert "sueño" in bienestar_msgs[0]["preview"]

    logs = (await db.execute(select(AlertaLog).where(AlertaLog.tipo == "bienestar"))).scalars().all()
    assert len(logs) == 1

    # Re-running the check the same day must not duplicate the alert
    assert await revisar_bienestar(db, jugador, HOY) is False
    logs = (await db.execute(select(AlertaLog).where(AlertaLog.tipo == "bienestar"))).scalars().all()
    assert len(logs) == 1


async def test_bienestar_normal_no_alerta(client: AsyncClient, db, seed_data):
    jugador = seed_data["jugadores"][1]
    for dias in (1, 2):
        db.add(Checkin(
            jugador_id=jugador.id, fecha=HOY - timedelta(days=dias), asistencia=True,
            sueno=5, energia=5, animo=5, dolor_pre=2,
        ))
    await db.commit()

    await client.post("/api/checkin", json={
        "jugador_id": jugador.id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 5, "energia": 5, "animo": 5, "dolor_pre": 2,
    })
    assert not any(m["template"] == "alerta_bienestar" for m in get_provider().sent)


async def test_alerta_carga_semanal_alta(client: AsyncClient, db, seed_data):
    categoria = seed_data["categoria"]
    categoria.umbral_alerta_carga = 500
    await db.commit()

    jugador = seed_data["jugadores"][2]
    await client.post("/api/checkin", json={
        "jugador_id": jugador.id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 5, "energia": 5, "animo": 5, "dolor_pre": 2,
    })
    # rpe 8 × 90 min = 720 > umbral 500
    resp = await client.post("/api/checkout", json={
        "jugador_id": jugador.id, "fecha": HOY.isoformat(), "rpe": 8,
    })
    assert resp.status_code == 201

    provider = get_provider()
    carga_msgs = [m for m in provider.sent if m["template"] == "alerta_carga"]
    assert len(carga_msgs) == 1
    assert "720" in carga_msgs[0]["preview"]
    assert "500" in carga_msgs[0]["preview"]

    logs = (await db.execute(select(AlertaLog).where(AlertaLog.tipo == "carga_alta"))).scalars().all()
    assert len(logs) == 1


async def test_carga_aguda_y_acwr(db, seed_data):
    jugador = seed_data["jugadores"][0]
    cargas = [(3, 400), (10, 300), (17, 200), (24, 100)]  # (días atrás, carga)
    for dias, carga in cargas:
        db.add(Checkout(
            jugador_id=jugador.id, fecha=HOY - timedelta(days=dias),
            rpe=5, duracion_min=carga // 5, carga=carga,
        ))
    await db.commit()

    assert await carga_aguda(db, jugador.id, HOY) == 400          # solo la de hace 3 días
    acwr = await calcular_acwr(db, jugador.id, HOY)
    assert acwr == 1.6                                            # 400 / (1000/4)


async def test_acwr_sin_historial_es_none(db, seed_data):
    assert await calcular_acwr(db, seed_data["jugadores"][1].id, HOY) is None


async def test_acwr_con_un_solo_registro_es_none(db, seed_data):
    """Cold start: a single recent session must NOT produce ACWR 4.0."""
    jugador = seed_data["jugadores"][1]
    db.add(Checkout(jugador_id=jugador.id, fecha=HOY, rpe=7, duracion_min=90, carga=630))
    await db.commit()
    assert await calcular_acwr(db, jugador.id, HOY) is None


async def test_acwr_historial_reciente_pero_corto_es_none(db, seed_data):
    """4 sessions all inside the acute window still lack a chronic base."""
    jugador = seed_data["jugadores"][1]
    for dias in (0, 1, 2, 3):
        db.add(Checkout(
            jugador_id=jugador.id, fecha=HOY - timedelta(days=dias),
            rpe=5, duracion_min=60, carga=300,
        ))
    await db.commit()
    assert await calcular_acwr(db, jugador.id, HOY) is None
