import pytest
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import Jugador, Recordatorio, Staff
from app.messaging import get_provider
from app.services.recordatorios import evaluar_recordatorios, hora_objetivo
from app.services.dashboard import datos_categoria

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings

HOY = date.today()
ADMIN_PASS = settings.admin_password


async def _login_admin(client: AsyncClient) -> None:
    resp = await client.post("/admin/super", data={"password": ADMIN_PASS})
    assert resp.status_code == 303


# ---------- Auth admin ----------

async def test_admin_requiere_login(client: AsyncClient, seed_data):
    resp = await client.get("/admin/test-club")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/login"


async def test_admin_login_incorrecto(client: AsyncClient):
    resp = await client.post("/admin/super", data={"password": "mala"})
    assert resp.status_code == 200
    assert "Contraseña incorrecta" in resp.text


async def test_admin_login_y_vista_dia(client: AsyncClient, seed_data):
    await _login_admin(client)
    resp = await client.get("/admin/test-club")
    assert resp.status_code == 200
    assert "Test Club" in resp.text
    assert "Pérez" in resp.text  # jugadores listados


# ---------- CRUD ----------

async def test_crear_y_desactivar_jugador(client: AsyncClient, db, seed_data):
    await _login_admin(client)
    cat = seed_data["categoria"]

    resp = await client.post("/admin/test-club/jugadores", data={
        "nombre": "Nuevo", "apellido": "Fichaje", "categoria_id": cat.id,
    })
    assert resp.status_code == 303

    nuevo = (await db.execute(
        select(Jugador).where(Jugador.apellido == "Fichaje")
    )).scalar_one()
    assert nuevo.activo is True

    resp = await client.post(f"/admin/test-club/jugadores/{nuevo.id}/toggle")
    assert resp.status_code == 303
    await db.refresh(nuevo)
    assert nuevo.activo is False


async def test_crear_staff(client: AsyncClient, db, seed_data):
    await _login_admin(client)
    resp = await client.post("/admin/test-club/staff", data={
        "nombre": "Nuevo PF", "telefono": "56911112222", "rol": "PF",
        "recibe_alertas": "true",
    })
    assert resp.status_code == 303
    nuevo = (await db.execute(select(Staff).where(Staff.nombre == "Nuevo PF"))).scalar_one()
    assert nuevo.recibe_alertas is True
    assert nuevo.recibe_resumen is False


async def test_editar_categoria(client: AsyncClient, db, seed_data):
    await _login_admin(client)
    cat = seed_data["categoria"]
    resp = await client.post(f"/admin/test-club/categorias/{cat.id}/editar", data={
        "hora_inicio": "17:00", "hora_fin": "18:30", "hora_resumen": "20:00",
        "min_checkins_semaforo": "5", "umbral_alerta_carga": "900",
        "dias": ["1", "3"],
    })
    assert resp.status_code == 303
    await db.refresh(cat)
    assert cat.hora_inicio == "17:00"
    assert cat.min_checkins_semaforo == 5
    assert cat.dias_entrenamiento == [1, 3]


# ---------- Reenvío manual ----------

async def test_reenvio_manual_semaforo(client: AsyncClient, db, seed_data):
    await _login_admin(client)
    jugador = seed_data["jugadores"][0]
    await client.post("/api/checkin", json={
        "jugador_id": jugador.id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 5, "energia": 5, "animo": 5, "dolor_pre": 2,
    })
    provider = get_provider()
    provider.sent.clear()

    cat = seed_data["categoria"]
    resp = await client.post(f"/admin/test-club/categorias/{cat.id}/reenviar-semaforo")
    assert resp.status_code == 303
    assert any(m["template"] == "semaforo_diario" for m in provider.sent)

    # Reenviar de nuevo: vuelve a salir (reset explícito del claim)
    provider.sent.clear()
    await client.post(f"/admin/test-club/categorias/{cat.id}/reenviar-semaforo")
    assert any(m["template"] == "semaforo_diario" for m in provider.sent)


# ---------- Recordatorios ----------

async def test_hora_objetivo():
    cat = type("C", (), {"hora_inicio": "16:00"})()
    rec_fijo = type("R", (), {"hora": "10:30", "minutos_antes": None})()
    rec_rel = type("R", (), {"hora": None, "minutos_antes": 30})()
    assert hora_objetivo(rec_fijo, cat) == "10:30"
    assert hora_objetivo(rec_rel, cat) == "15:30"


async def test_recordatorio_envia_y_claim_diario(db, seed_data):
    cat = seed_data["categoria"]
    rec = Recordatorio(
        categoria_id=cat.id, nombre="Test", mensaje="Comparte el QR",
        minutos_antes=30, condicion_min_checkins=5,
    )
    db.add(rec)
    await db.commit()

    provider = get_provider()

    # Antes de la hora objetivo (15:30): no envía
    enviados = await evaluar_recordatorios(db, cat, HOY, "15:00")
    assert enviados == 0

    # Después de la hora objetivo, 0 checkins < 5: envía
    enviados = await evaluar_recordatorios(db, cat, HOY, "15:31")
    assert enviados == 1
    msgs = [m for m in provider.sent if m["template"] == "recordatorio_checkin"]
    assert len(msgs) == 1
    assert "Comparte el QR" in msgs[0]["preview"]

    # Mismo día de nuevo: claim impide duplicado
    enviados = await evaluar_recordatorios(db, cat, HOY, "15:45")
    assert enviados == 0


async def test_recordatorio_condicion_no_cumplida(client: AsyncClient, db, seed_data):
    cat = seed_data["categoria"]
    rec = Recordatorio(
        categoria_id=cat.id, nombre="Condicional", mensaje="Faltan check-ins",
        minutos_antes=0, condicion_min_checkins=1,  # solo si 0 check-ins
    )
    db.add(rec)
    await db.commit()

    # Ya hay 1 checkin → condición (checkins < 1) es falsa → no envía y claim queda tomado
    jugador = seed_data["jugadores"][0]
    await client.post("/api/checkin", json={
        "jugador_id": jugador.id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 5, "energia": 5, "animo": 5, "dolor_pre": 2,
    })
    provider = get_provider()
    provider.sent.clear()

    enviados = await evaluar_recordatorios(db, cat, HOY, "23:59")
    assert enviados == 0
    assert not any(m["template"] == "recordatorio_checkin" for m in provider.sent)


# ---------- Dashboard ----------

async def test_dashboard_requiere_password(client: AsyncClient, seed_data):
    resp = await client.get("/d/test-club")
    assert resp.status_code == 303
    assert "/d/test-club/login" in resp.headers["location"]

    resp = await client.post("/d/test-club/login", data={"password": "mala"})
    assert "Contraseña incorrecta" in resp.text

    resp = await client.post("/d/test-club/login", data={"password": "test123"})
    assert resp.status_code == 303

    resp = await client.get("/d/test-club")
    assert resp.status_code == 200
    assert "Sub-13" in resp.text


async def test_dashboard_datos(client: AsyncClient, db, seed_data):
    j = seed_data["jugadores"]
    # j0: 2 días de proceso completo; j1: 1 checkin sin checkout
    for dias in (0, 1):
        fecha = (HOY - timedelta(days=dias)).isoformat()
        await client.post("/api/checkin", json={
            "jugador_id": j[0].id, "fecha": fecha, "asistencia": True,
            "sueno": 5, "energia": 5, "animo": 6, "dolor_pre": 2,
        })
        await client.post("/api/checkout", json={"jugador_id": j[0].id, "fecha": fecha, "rpe": 6})
    await client.post("/api/checkin", json={
        "jugador_id": j[1].id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 6, "energia": 6, "animo": 6, "dolor_pre": 1,
    })

    d = await datos_categoria(db, seed_data["categoria"], HOY)
    assert d["dias_activos"] == 2
    assert d["total_checkins"] == 3
    assert d["total_checkouts"] == 2

    fila_j0 = next(f for f in d["filas"] if f["jugador"].id == j[0].id)
    assert fila_j0["adhesion"] == 100      # 2 registros / 2 días activos
    assert fila_j0["proceso"] == 100       # 2 checkouts / 2 asistencias
    fila_j1 = next(f for f in d["filas"] if f["jugador"].id == j[1].id)
    assert fila_j1["adhesion"] == 50
    assert fila_j1["proceso"] == 0

    assert d["hooper"]["sueno"] is not None
    assert sum(d["rpe_dist"].values()) == 2
    assert len(d["insights"]) >= 1
