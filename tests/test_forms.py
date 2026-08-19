import json
import re

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_form_page_ok(client: AsyncClient, seed_data):
    resp = await client.get("/f/test-club/Sub-13")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "Test Club" in html
    assert "¿Qué quieres registrar?" in html
    # jugadores embedded as JSON for the dropdown
    match = re.search(r'<script id="form-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert match, "form-data JSON script tag missing"
    data = json.loads(match.group(1))
    assert {"id": seed_data["jugadores"][0].id, "nombre": "Pérez, Juan"} in data["jugadores"]
    assert data["categoria_id"] == seed_data["categoria"].id


async def test_form_page_club_inexistente(client: AsyncClient, seed_data):
    resp = await client.get("/f/no-existe/Sub-13")
    assert resp.status_code == 404


async def test_form_page_categoria_inexistente(client: AsyncClient, seed_data):
    resp = await client.get("/f/test-club/Sub-99")
    assert resp.status_code == 404


async def test_qr_png(client: AsyncClient, seed_data):
    resp = await client.get("/qr/test-club/Sub-13.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes


async def test_qr_page(client: AsyncClient, seed_data):
    resp = await client.get("/qr/test-club/Sub-13")
    assert resp.status_code == 200
    html = resp.text
    assert "Registro diario" in html
    assert "/qr/test-club/Sub-13.png" in html


async def test_qr_club_inexistente(client: AsyncClient, seed_data):
    resp = await client.get("/qr/no-existe/Sub-13.png")
    assert resp.status_code == 404
