import pytest
from datetime import date

from httpx import AsyncClient

from app.messaging import get_provider
from app.services.resumen import generar_resumen, enviar_resumen

pytestmark = pytest.mark.asyncio(loop_scope="session")

HOY = date.today()


async def test_generar_resumen_completo(client: AsyncClient, db, seed_data):
    j = seed_data["jugadores"]
    # j0: checkin con molestia + checkout
    await client.post("/api/checkin", json={
        "jugador_id": j[0].id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 5, "energia": 5, "animo": 5, "dolor_pre": 3,
        "molestia_previa": True, "molestia_zona": "Rodilla",
    })
    await client.post("/api/checkout", json={
        "jugador_id": j[0].id, "fecha": HOY.isoformat(), "rpe": 7,
    })
    # j1: checkin sin checkout
    await client.post("/api/checkin", json={
        "jugador_id": j[1].id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 6, "energia": 6, "animo": 6, "dolor_pre": 1,
    })
    # j2: inasistencia
    await client.post("/api/checkin", json={
        "jugador_id": j[2].id, "fecha": HOY.isoformat(), "asistencia": False,
        "motivo_inasistencia": "Enfermedad",
    })

    r = await generar_resumen(db, seed_data["categoria"], HOY)
    assert r["total_jugadores"] == 3
    assert r["asistieron"] == 2
    assert len(r["inasistencias"]) == 1 and "Enfermedad" in r["inasistencias"][0]
    assert len(r["molestias"]) == 1 and "Rodilla" in r["molestias"][0]
    assert len(r["sin_checkout"]) == 1
    assert j[1].nombre in r["sin_checkout"][0]
    assert r["rpe_promedio"] == 7.0
    assert r["carga_promedio"] == 7 * 90


async def test_enviar_resumen_una_sola_vez(client: AsyncClient, db, seed_data):
    jugador = seed_data["jugadores"][0]
    await client.post("/api/checkin", json={
        "jugador_id": jugador.id, "fecha": HOY.isoformat(), "asistencia": True,
        "sueno": 5, "energia": 5, "animo": 5, "dolor_pre": 2,
    })
    provider = get_provider()
    provider.sent.clear()

    assert await enviar_resumen(db, seed_data["categoria"], HOY) is True
    resumenes = [m for m in provider.sent if m["template"] == "resumen_diario"]
    assert len(resumenes) == 1
    assert "1/3" in resumenes[0]["preview"]

    assert await enviar_resumen(db, seed_data["categoria"], HOY) is False
    assert len([m for m in provider.sent if m["template"] == "resumen_diario"]) == 1


async def test_resumen_dia_sin_actividad(db, seed_data):
    """A summary with zero submissions is still sent — the DT should know nobody registered."""
    assert await enviar_resumen(db, seed_data["categoria"], HOY) is True
    resumen = next(m for m in get_provider().sent if m["template"] == "resumen_diario")
    assert "0/3" in resumen["preview"]
    assert "Ninguna" in resumen["preview"]
