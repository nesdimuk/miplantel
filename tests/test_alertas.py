import pytest
from datetime import date

from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import AlertaLog
from app.messaging import get_provider

pytestmark = pytest.mark.asyncio(loop_scope="session")

TODAY = date.today().isoformat()


async def test_checkin_con_molestia_alerta_al_staff(client: AsyncClient, db, seed_data):
    jugador = seed_data["jugadores"][0]
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": True,
        "sueno": 5, "energia": 5, "animo": 5, "dolor_pre": 5,
        "molestia_previa": True,
        "molestia_zona": "Rodilla",
    })
    assert resp.status_code == 201

    provider = get_provider()
    assert len(provider.sent) == 1
    msg = provider.sent[0]
    assert msg["to"] == seed_data["staff"].telefono_whatsapp
    assert msg["template"] == "alerta_molestia"
    assert "Rodilla" in msg["preview"]
    assert "check-in" in msg["preview"]

    logs = (await db.execute(select(AlertaLog).where(AlertaLog.tipo == "molestia"))).scalars().all()
    assert len(logs) == 1
    assert logs[0].estado_envio == "sent"
    assert logs[0].wamid is not None
    assert logs[0].jugador_id == jugador.id


async def test_checkin_inasistencia_alerta_con_motivo(client: AsyncClient, db, seed_data):
    jugador = seed_data["jugadores"][1]
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": False,
        "motivo_inasistencia": "Enfermedad",
    })
    assert resp.status_code == 201

    provider = get_provider()
    assert len(provider.sent) == 1
    assert provider.sent[0]["template"] == "alerta_inasistencia"
    assert "Enfermedad" in provider.sent[0]["preview"]

    logs = (await db.execute(select(AlertaLog).where(AlertaLog.tipo == "inasistencia"))).scalars().all()
    assert len(logs) == 1


async def test_checkin_normal_no_genera_alertas(client: AsyncClient, db, seed_data):
    jugador = seed_data["jugadores"][2]
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": True,
        "sueno": 6, "energia": 6, "animo": 6, "dolor_pre": 1,
        "molestia_previa": False,
    })
    assert resp.status_code == 201
    assert len(get_provider().sent) == 0
    logs = (await db.execute(select(AlertaLog))).scalars().all()
    assert logs == []


async def test_checkout_con_molestia_nueva_alerta(client: AsyncClient, db, seed_data):
    jugador = seed_data["jugadores"][0]
    await client.post("/api/checkin", json={
        "jugador_id": jugador.id, "fecha": TODAY, "asistencia": True,
        "sueno": 5, "energia": 5, "animo": 5, "dolor_pre": 2,
    })
    resp = await client.post("/api/checkout", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "rpe": 8,
        "molestia_nueva": True,
        "molestia_zona": "Tobillo/pie",
    })
    assert resp.status_code == 201

    provider = get_provider()
    assert len(provider.sent) == 1
    assert "Tobillo/pie" in provider.sent[0]["preview"]
    assert "check-out" in provider.sent[0]["preview"]


async def test_reintento_con_exito_al_tercer_intento(client: AsyncClient, db, seed_data):
    provider = get_provider()
    provider.fail_times = 2  # first two attempts fail, third succeeds

    jugador = seed_data["jugadores"][1]
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": False,
        "motivo_inasistencia": "Viaje",
    })
    assert resp.status_code == 201

    logs = (await db.execute(select(AlertaLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].estado_envio == "sent"


async def test_reintentos_agotados_marca_failed(client: AsyncClient, db, seed_data):
    provider = get_provider()
    provider.fail_times = 3  # all attempts fail

    jugador = seed_data["jugadores"][2]
    resp = await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": False,
        "motivo_inasistencia": "Lesión",
    })
    assert resp.status_code == 201  # el registro del jugador nunca falla

    logs = (await db.execute(select(AlertaLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].estado_envio == "failed"
    assert "fake_error" in logs[0].respuesta_api


# ---------- Webhook ----------

async def test_webhook_verificacion_ok(client: AsyncClient):
    resp = await client.get("/webhooks/whatsapp", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "assist_verify_token",
        "hub.challenge": "12345",
    })
    assert resp.status_code == 200
    assert resp.text == "12345"


async def test_webhook_verificacion_token_invalido(client: AsyncClient):
    resp = await client.get("/webhooks/whatsapp", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "token-malo",
        "hub.challenge": "12345",
    })
    assert resp.status_code == 403


async def test_webhook_actualiza_estado_entrega(client: AsyncClient, db, seed_data):
    # Generate an alert to get a wamid
    jugador = seed_data["jugadores"][0]
    await client.post("/api/checkin", json={
        "jugador_id": jugador.id,
        "fecha": TODAY,
        "asistencia": False,
        "motivo_inasistencia": "Estudios",
    })
    log = (await db.execute(select(AlertaLog))).scalars().one()
    assert log.estado_envio == "sent"

    # Meta-style status payload
    resp = await client.post("/webhooks/whatsapp", json={
        "entry": [{"changes": [{"value": {"statuses": [
            {"id": log.wamid, "status": "delivered"},
        ]}}]}],
    })
    assert resp.status_code == 200

    await db.refresh(log)
    assert log.estado_envio == "delivered"

    # "read" upgrades, later "delivered" must not downgrade
    await client.post("/webhooks/whatsapp", json={
        "entry": [{"changes": [{"value": {"statuses": [{"id": log.wamid, "status": "read"}]}}]}],
    })
    await db.refresh(log)
    assert log.estado_envio == "read"

    await client.post("/webhooks/whatsapp", json={
        "entry": [{"changes": [{"value": {"statuses": [{"id": log.wamid, "status": "delivered"}]}}]}],
    })
    await db.refresh(log)
    assert log.estado_envio == "read"  # no downgrade
