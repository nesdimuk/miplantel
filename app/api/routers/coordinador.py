from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import hash_password, make_token
from app.api.templating import templates
from app.db.engine import get_db
from app.db.models import Categoria, Checkin, Checkout, Club, Jugador, Staff

router = APIRouter()

COORD_COOKIE = "mp_coord"


def _require_coord(request: Request, club_slug: str) -> bool:
    token = request.cookies.get(COORD_COOKIE)
    return token == make_token(f"coord:{club_slug}")


@router.get("/coord/{club_slug}/login")
async def coord_login_page(request: Request, club_slug: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    return templates.TemplateResponse(request, "coord_login.html", {"club": club, "error": None})


@router.post("/coord/{club_slug}/login")
async def coord_login(
    request: Request,
    club_slug: str,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    coordinador = (await db.execute(
        select(Staff).where(
            Staff.club_id == club.id,
            Staff.es_coordinador == True,  # noqa: E712
            Staff.activo == True,  # noqa: E712
        )
    )).scalars().first()

    if not coordinador or not coordinador.password_coord or \
            hash_password(password) != coordinador.password_coord:
        return templates.TemplateResponse(request, "coord_login.html", {
            "club": club, "error": "Contraseña incorrecta",
        })

    resp = RedirectResponse(f"/coord/{club_slug}", status_code=303)
    resp.set_cookie(COORD_COOKIE, make_token(f"coord:{club_slug}"), httponly=True, max_age=60 * 60 * 24)
    return resp


@router.get("/coord/{club_slug}")
async def coord_dashboard(
    request: Request,
    club_slug: str,
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    if not _require_coord(request, club_slug):
        return RedirectResponse(f"/coord/{club_slug}/login", status_code=303)

    hoy = datetime.now(ZoneInfo(club.timezone)).date()

    categorias = (await db.execute(
        select(Categoria).where(Categoria.club_id == club.id, Categoria.activo == True)  # noqa: E712
        .order_by(Categoria.nombre)
    )).scalars().all()

    # Build per-category KPIs
    resumen = []
    totales = {"jugadores": 0, "checkins": 0, "checkouts": 0}

    for cat in categorias:
        total_jug = (await db.execute(
            select(func.count(Jugador.id)).where(
                Jugador.categoria_id == cat.id, Jugador.activo == True  # noqa: E712
            )
        )).scalar_one()

        checkins_hoy = (await db.execute(
            select(func.count(Checkin.id))
            .join(Jugador, Checkin.jugador_id == Jugador.id)
            .where(Jugador.categoria_id == cat.id, Checkin.fecha == hoy, Checkin.asistencia == True)  # noqa: E712
        )).scalar_one()

        checkouts_hoy = (await db.execute(
            select(func.count(Checkout.id))
            .join(Jugador, Checkout.jugador_id == Jugador.id)
            .where(Jugador.categoria_id == cat.id, Checkout.fecha == hoy)
        )).scalar_one()

        # Hooper promedio hoy
        rows = (await db.execute(
            select(Checkin)
            .join(Jugador, Checkin.jugador_id == Jugador.id)
            .where(Jugador.categoria_id == cat.id, Checkin.fecha == hoy, Checkin.asistencia == True)  # noqa: E712
        )).scalars().all()

        hoopers = []
        for c in rows:
            if all(getattr(c, f) is not None for f in ("sueno", "energia", "dolor_pre", "estres")):
                hoopers.append((c.sueno + c.energia + (8 - c.dolor_pre) + (8 - c.estres)) / 4)
        hooper_prom = round(sum(hoopers) / len(hoopers), 1) if hoopers else None

        # Entrenador de esta categoría
        dt = (await db.execute(
            select(Staff).where(
                Staff.club_id == club.id,
                Staff.activo == True,  # noqa: E712
                Staff.rol == "DT",
            )
        )).scalars().all()
        entrenador = next(
            (s.nombre for s in dt if s.categoria_ids and cat.id in s.categoria_ids),
            "—"
        )

        pct_checkin = round(checkins_hoy / total_jug * 100) if total_jug else 0
        pct_checkout = round(checkouts_hoy / checkins_hoy * 100) if checkins_hoy else 0

        semaforo = "🟢" if hooper_prom and hooper_prom >= 5.0 else \
                   "🟡" if hooper_prom and hooper_prom >= 3.5 else \
                   "🔴" if hooper_prom else "⬜"

        resumen.append({
            "categoria": cat,
            "entrenador": entrenador,
            "total_jug": total_jug,
            "checkins": checkins_hoy,
            "checkouts": checkouts_hoy,
            "pct_checkin": pct_checkin,
            "pct_checkout": pct_checkout,
            "hooper": hooper_prom,
            "semaforo": semaforo,
        })

        totales["jugadores"] += total_jug
        totales["checkins"] += checkins_hoy
        totales["checkouts"] += checkouts_hoy

    return templates.TemplateResponse(request, "coord_dashboard.html", {
        "club": club,
        "resumen": resumen,
        "totales": totales,
        "hoy": hoy,
    })


async def _get_club(db: AsyncSession, slug: str) -> Club:
    from fastapi import HTTPException
    club = (await db.execute(
        select(Club).where(Club.slug == slug, Club.activo == True)  # noqa: E712
    )).scalar_one_or_none()
    if not club:
        raise HTTPException(404, "Club no encontrado")
    return club
