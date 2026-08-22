import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import segno
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.db.models import Club, Categoria, Jugador

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parents[2] / "templates")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


@router.get("/f/{club_slug}/{categoria_nombre}")
async def form_page(
    request: Request,
    club_slug: str,
    categoria_nombre: str,
    db: AsyncSession = Depends(get_db),
):
    """Mobile-first check-in/check-out form for players."""
    club = await _get_club_or_404(db, club_slug)
    categoria = await _get_categoria_or_404(db, club.id, categoria_nombre)

    result = await db.execute(
        select(Jugador)
        .where(Jugador.categoria_id == categoria.id, Jugador.activo == True)  # noqa: E712
        .order_by(Jugador.apellido, Jugador.nombre)
    )
    jugadores = result.scalars().all()

    hoy = datetime.now(ZoneInfo(club.timezone))
    fecha_display = f"{DIAS[hoy.weekday()]} {hoy.day} de {MESES[hoy.month - 1]}"

    return templates.TemplateResponse(request, "form.html", {
        "club_nombre": club.nombre,
        "categoria_nombre": categoria.nombre,
        "color_primario": club.color_primario or "#C9A227",
        "color_secundario": club.color_secundario or "#1A1A1A",
        "fecha_display": fecha_display,
        "form_data": {
            "categoria_id": categoria.id,
            "fecha": hoy.date().isoformat(),
            "jugadores": [{"id": j.id, "nombre": f"{j.apellido}, {j.nombre}"} for j in jugadores],
        },
    })


@router.get("/qr/{club_slug}/{categoria_nombre}.png")
async def qr_image(
    request: Request,
    club_slug: str,
    categoria_nombre: str,
    db: AsyncSession = Depends(get_db),
):
    """QR code PNG pointing to the category form."""
    club = await _get_club_or_404(db, club_slug)
    await _get_categoria_or_404(db, club.id, categoria_nombre)

    url = _form_url(request, club_slug, categoria_nombre)
    buf = io.BytesIO()
    segno.make(url, error="q").save(buf, kind="png", scale=12, border=2, dark="#0d47a1")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/qr/{club_slug}/{categoria_nombre}")
async def qr_page(
    request: Request,
    club_slug: str,
    categoria_nombre: str,
    db: AsyncSession = Depends(get_db),
):
    """Printable page with the QR code and instructions for the locker room wall."""
    club = await _get_club_or_404(db, club_slug)
    categoria = await _get_categoria_or_404(db, club.id, categoria_nombre)

    return templates.TemplateResponse(request, "qr.html", {
        "club_nombre": club.nombre,
        "categoria_nombre": categoria.nombre,
        "qr_src": f"/qr/{club_slug}/{categoria_nombre}.png",
        "form_url": _form_url(request, club_slug, categoria_nombre),
    })


def _form_url(request: Request, club_slug: str, categoria_nombre: str) -> str:
    base = settings.base_url or str(request.base_url).rstrip("/")
    return f"{base}/f/{club_slug}/{categoria_nombre}"


async def _get_club_or_404(db: AsyncSession, slug: str) -> Club:
    result = await db.execute(select(Club).where(Club.slug == slug, Club.activo == True))  # noqa: E712
    club = result.scalar_one_or_none()
    if not club:
        raise HTTPException(404, "Club no encontrado")
    return club


async def _get_categoria_or_404(db: AsyncSession, club_id: int, nombre: str) -> Categoria:
    result = await db.execute(
        select(Categoria).where(
            Categoria.club_id == club_id,
            Categoria.nombre == nombre,
            Categoria.activo == True,  # noqa: E712
        )
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Categoría no encontrada")
    return cat
