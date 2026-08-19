from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import DASH_COOKIE, hash_password, make_token, require_dash
from app.api.templating import templates
from app.db.engine import get_db
from app.db.models import Categoria, Club
from app.services import dashboard as dashboard_svc

router = APIRouter()


@router.get("/d/{club_slug}/login")
async def dash_login_page(request: Request, club_slug: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    return templates.TemplateResponse(request, "dash_login.html", {"club": club, "error": None})


@router.post("/d/{club_slug}/login")
async def dash_login(
    request: Request,
    club_slug: str,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    if not club.password_dashboard or hash_password(password) != club.password_dashboard:
        return templates.TemplateResponse(request, "dash_login.html", {
            "club": club, "error": "Contraseña incorrecta",
        })
    resp = RedirectResponse(f"/d/{club_slug}", status_code=303)
    resp.set_cookie(DASH_COOKIE, make_token(f"dash:{club_slug}"), httponly=True, max_age=60 * 60 * 24)
    return resp


@router.get("/d/{club_slug}")
async def dashboard_page(
    request: Request,
    club_slug: str,
    categoria_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    if not require_dash(request, club_slug):
        return RedirectResponse(f"/d/{club_slug}/login", status_code=303)

    categorias = (await db.execute(
        select(Categoria).where(Categoria.club_id == club.id, Categoria.activo == True)  # noqa: E712
        .order_by(Categoria.nombre)
    )).scalars().all()
    if not categorias:
        raise HTTPException(404, "El club no tiene categorías activas")

    categoria = next((c for c in categorias if c.id == categoria_id), categorias[0])
    hoy = datetime.now(ZoneInfo(club.timezone)).date()
    datos = await dashboard_svc.datos_categoria(db, categoria, hoy)

    return templates.TemplateResponse(request, "dashboard.html", {
        "club": club,
        "categorias": categorias,
        "categoria": categoria,
        "d": datos,
    })


async def _get_club(db: AsyncSession, slug: str) -> Club:
    club = (await db.execute(
        select(Club).where(Club.slug == slug, Club.activo == True)  # noqa: E712
    )).scalar_one_or_none()
    if not club:
        raise HTTPException(404, "Club no encontrado")
    return club
