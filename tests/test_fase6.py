"""Fase 6: registro self-service, login por club y scoping multi-tenant."""
import pytest

from httpx import AsyncClient
from sqlalchemy import select

from app.api.auth import hash_password
from app.config import settings
from app.db.models import Club, Jugador

pytestmark = pytest.mark.asyncio(loop_scope="session")


REGISTRO = {
    "nombre": "Deportes La Serena",
    "email": "captacion@laserena.cl",
    "password": "granate2026",
    "timezone": "America/Santiago",
}


async def _login_club(client: AsyncClient, email="club@test.cl", password="clubpass123"):
    return await client.post("/admin/login", data={"email": email, "password": password})


# ---------- Landing y registro ----------

async def test_landing_publica(client: AsyncClient):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Registra tu club" in resp.text


async def test_registro_crea_club_y_entra_directo(client: AsyncClient, db):
    resp = await client.post("/registro", data=REGISTRO)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/deportes-la-serena"
    assert "assist_admin" in resp.cookies

    club = (await db.execute(select(Club).where(Club.slug == "deportes-la-serena"))).scalar_one()
    assert club.email == "captacion@laserena.cl"
    assert club.password_admin == hash_password("granate2026")
    assert club.password_dashboard == hash_password("granate2026")

    # Con la cookie puesta, ve su guía de inicio (aún sin categorías)
    resp = await client.get("/admin/deportes-la-serena")
    assert resp.status_code == 200
    assert "Primeros pasos" in resp.text or "Bienvenido" in resp.text


async def test_registro_email_duplicado(client: AsyncClient, seed_data):
    resp = await client.post("/registro", data={**REGISTRO, "email": "club@test.cl"})
    assert resp.status_code == 200
    assert "Ya existe un club" in resp.text


async def test_registro_password_corta(client: AsyncClient):
    resp = await client.post("/registro", data={**REGISTRO, "password": "corta"})
    assert resp.status_code == 200
    assert "al menos 8 caracteres" in resp.text


async def test_registro_slug_unico_con_nombre_repetido(client: AsyncClient, db):
    await client.post("/registro", data=REGISTRO)
    client.cookies.clear()
    resp = await client.post("/registro", data={**REGISTRO, "email": "otro@laserena.cl"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/deportes-la-serena-2"


# ---------- Login por club ----------

async def test_login_club_ok(client: AsyncClient, seed_data):
    resp = await _login_club(client)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/test-club"

    resp = await client.get("/admin/test-club")
    assert resp.status_code == 200
    assert "Test Club" in resp.text


async def test_login_club_password_incorrecta(client: AsyncClient, seed_data):
    resp = await _login_club(client, password="incorrecta")
    assert resp.status_code == 200
    assert "incorrectos" in resp.text


async def test_login_club_email_inexistente(client: AsyncClient, seed_data):
    resp = await _login_club(client, email="nadie@nada.cl")
    assert resp.status_code == 200
    assert "incorrectos" in resp.text


# ---------- Scoping multi-tenant ----------

async def test_club_no_ve_otro_club(client: AsyncClient, db, seed_data):
    otro = Club(
        nombre="Rival FC", slug="rival-fc", email="rival@fc.cl",
        password_admin=hash_password("rivalpass1"),
    )
    db.add(otro)
    await db.commit()

    await _login_club(client)  # cookie de test-club
    resp = await client.get("/admin/rival-fc")
    assert resp.status_code == 404
    resp = await client.get("/admin/rival-fc/jugadores")
    assert resp.status_code == 404


async def test_club_admin_home_redirige_a_su_club(client: AsyncClient, seed_data):
    await _login_club(client)
    resp = await client.get("/admin")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/test-club"


async def test_superadmin_ve_todos_los_clubes(client: AsyncClient, seed_data):
    resp = await client.post("/admin/super", data={"password": settings.admin_password})
    assert resp.status_code == 303

    resp = await client.get("/admin")
    assert resp.status_code == 200
    assert "Test Club" in resp.text

    resp = await client.get("/admin/test-club")
    assert resp.status_code == 200


# ---------- Alta masiva ----------

async def test_alta_masiva_jugadores(client: AsyncClient, db, seed_data):
    await _login_club(client)
    cat = seed_data["categoria"]
    lista = "Matías González\nSebastián Muñoz Rojas\n\n   \nDiego"
    resp = await client.post("/admin/test-club/jugadores/masivo", data={
        "categoria_id": cat.id, "lista": lista,
    })
    assert resp.status_code == 303

    nuevos = (await db.execute(
        select(Jugador).where(Jugador.nombre.in_(["Matías", "Sebastián", "Diego"]))
    )).scalars().all()
    assert len(nuevos) == 3
    seba = next(j for j in nuevos if j.nombre == "Sebastián")
    assert seba.apellido == "Muñoz Rojas"
    diego = next(j for j in nuevos if j.nombre == "Diego")
    assert diego.apellido == ""
