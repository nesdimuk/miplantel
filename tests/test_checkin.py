import pytest
from datetime import date
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")

TODAY = date.today().isoformat()


@pytest.mark.asyncio
async def test_checkin_asistencia_ok(client: AsyncClient, seed_data):
    jugador = seed_data["jugadores"][0]
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": True,
        "sueno": 5,
        "energia": 6,
        "animo": 6,
        "dolor_pre": 2,
        "molestia_previa": False,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["asistencia"] is True
    assert "feedback" in data
    assert data["feedback"]  # non-empty gamified message


@pytest.mark.asyncio
async def test_checkin_inasistencia_ok(client: AsyncClient, seed_data):
    jugador = seed_data["jugadores"][1]
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": False,
        "motivo_inasistencia": "Enfermedad",
    })
    assert resp.status_code == 201
    assert resp.json()["asistencia"] is False


@pytest.mark.asyncio
async def test_checkin_idempotente(client: AsyncClient, seed_data):
    jugador = seed_data["jugadores"][2]
    payload = {
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": True,
        "sueno": 4, "energia": 4, "animo": 4, "dolor_pre": 3,
    }
    r1 = await client.post("/api/checkin", json=payload)
    r2 = await client.post("/api/checkin", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]  # same record


@pytest.mark.asyncio
async def test_checkin_asistencia_sin_escalas_falla(client: AsyncClient, seed_data):
    jugador = seed_data["jugadores"][0]
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": True,
        # missing sueno, energia, animo, dolor_pre
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_checkin_inasistencia_sin_motivo_falla(client: AsyncClient, seed_data):
    jugador = seed_data["jugadores"][0]
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": False,
        # missing motivo_inasistencia
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_checkin_jugador_inexistente(client: AsyncClient, seed_data):
    resp = await client.post("/api/checkin", json={
        "jugador_id": 99999,
        "fecha": TODAY,
        "asistencia": True,
        "sueno": 4, "energia": 4, "animo": 4, "dolor_pre": 3,
    })
    assert resp.status_code == 404
