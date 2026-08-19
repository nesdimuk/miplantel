import pytest
from datetime import date
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")

TODAY = date.today().isoformat()


async def _do_checkin(client, jugador_id):
    return await client.post("/api/checkin", json={
        "jugador_id": jugador_id,
        "fecha": TODAY,
        "asistencia": True,
        "sueno": 5, "energia": 5, "animo": 5, "dolor_pre": 2,
    })


@pytest.mark.asyncio
async def test_checkout_sin_duracion_deriva_de_categoria(client: AsyncClient, seed_data):
    """Duration should be derived from categoria hora_inicio/hora_fin (16:00-17:30 = 90 min)."""
    jugador = seed_data["jugadores"][0]
    await _do_checkin(client, jugador.id)

    resp = await client.post("/api/checkout", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "rpe": 7,
        "fisico_post": 5,
        "rendimiento": 6,
        "molestia_nueva": False,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["duracion_min"] == 90          # 16:00 → 17:30
    assert data["carga"] == 7 * 90             # 630


@pytest.mark.asyncio
async def test_checkout_duracion_explicita_sobreescribe(client: AsyncClient, seed_data):
    """Staff can pass duracion_min explicitly to override (e.g. shortened session)."""
    jugador = seed_data["jugadores"][1]
    await _do_checkin(client, jugador.id)

    resp = await client.post("/api/checkout", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "rpe": 6,
        "duracion_min": 60,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["duracion_min"] == 60
    assert data["carga"] == 6 * 60


@pytest.mark.asyncio
async def test_checkout_idempotente(client: AsyncClient, seed_data):
    jugador = seed_data["jugadores"][2]
    await _do_checkin(client, jugador.id)

    payload = {"jugador_id": jugador.id, "fecha": TODAY, "rpe": 6}
    r1 = await client.post("/api/checkout", json=payload)
    r2 = await client.post("/api/checkout", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.asyncio
async def test_checkout_sin_checkin_falla(client: AsyncClient, seed_data):
    jugador = seed_data["jugadores"][0]
    resp = await client.post("/api/checkout", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "rpe": 7,
    })
    # jugador[0] ya tiene checkin de otro test — este test corre en DB limpia
    # pero el fixture seed_data NO hace checkin, así que debe fallar
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_checkout_rpe_fuera_de_rango(client: AsyncClient, seed_data):
    jugador = seed_data["jugadores"][0]
    resp = await client.post("/api/checkout", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "rpe": 11,  # > 10
    })
    assert resp.status_code == 422
