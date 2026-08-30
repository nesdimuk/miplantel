from datetime import datetime, date, timedelta, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import (
    ADMIN_COOKIE, SUPER_SCOPE, admin_scope, hash_password, make_token, require_admin,
)
from app.api.templating import templates
from app.config import settings
from app.db.engine import get_db
from app.db.models import (
    AlertaLog, Categoria, Checkin, Checkout, Club, Jugador, Recordatorio, SesionDia, Staff,
)
from app.services import resumen as resumen_svc
from app.services import semaforo as semaforo_svc

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
login_router = APIRouter(prefix="/admin")


# ---------- Login de clubes (email + contraseña) ----------

def _set_admin_cookie(resp: RedirectResponse, scope: str) -> RedirectResponse:
    resp.set_cookie(ADMIN_COOKIE, make_token(scope), httponly=True, max_age=60 * 60 * 12)
    return resp


@login_router.get("/login")
async def login_page(request: Request):
    scope = admin_scope(request)
    if scope:
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(request, "admin/login.html", {"error": None})


@login_router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    club = (await db.execute(
        select(Club).where(Club.email == email.strip().lower(), Club.activo == True)  # noqa: E712
    )).scalar_one_or_none()
    if not club or not club.password_admin or club.password_admin != hash_password(password):
        return templates.TemplateResponse(request, "admin/login.html", {"error": "Email o contraseña incorrectos"})
    return _set_admin_cookie(RedirectResponse(f"/admin/{club.slug}", status_code=303), f"club:{club.slug}")


# ---------- Login superadmin (nosotros) ----------

@login_router.get("/super")
async def super_login_page(request: Request):
    if admin_scope(request) == SUPER_SCOPE:
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(request, "admin/super_login.html", {"error": None})


@login_router.post("/super")
async def super_login(request: Request, password: str = Form(...)):
    if password != settings.admin_password:
        return templates.TemplateResponse(request, "admin/super_login.html", {"error": "Contraseña incorrecta"})
    return _set_admin_cookie(RedirectResponse("/admin", status_code=303), SUPER_SCOPE)


@login_router.get("/logout")
async def logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


# ---------- Clubes ----------

@router.get("")
async def admin_home(request: Request, db: AsyncSession = Depends(get_db)):
    scope = admin_scope(request)
    if scope != SUPER_SCOPE:
        return RedirectResponse(f"/admin/{scope.removeprefix('club:')}", status_code=303)

    from sqlalchemy import func as sqlfunc
    clubes = (await db.execute(select(Club).order_by(Club.nombre))).scalars().all()
    hoy = datetime.now().date()
    hace7 = hoy - timedelta(days=6)

    filas = []
    for club in clubes:
        # Jugadores activos
        n_jugadores = (await db.execute(
            select(sqlfunc.count(Jugador.id))
            .join(Categoria, Jugador.categoria_id == Categoria.id)
            .where(Categoria.club_id == club.id, Jugador.activo == True)  # noqa: E712
        )).scalar_one()

        # Categorías activas
        n_cats = (await db.execute(
            select(sqlfunc.count(Categoria.id))
            .where(Categoria.club_id == club.id, Categoria.activo == True)  # noqa: E712
        )).scalar_one()

        # Check-ins de hoy
        checkins_hoy = (await db.execute(
            select(sqlfunc.count(Checkin.id))
            .join(Jugador, Checkin.jugador_id == Jugador.id)
            .join(Categoria, Jugador.categoria_id == Categoria.id)
            .where(Categoria.club_id == club.id, Checkin.fecha == hoy, Checkin.asistencia == True)  # noqa: E712
        )).scalar_one()

        # Check-outs de hoy
        checkouts_hoy = (await db.execute(
            select(sqlfunc.count(Checkout.id))
            .join(Jugador, Checkout.jugador_id == Jugador.id)
            .join(Categoria, Jugador.categoria_id == Categoria.id)
            .where(Categoria.club_id == club.id, Checkout.fecha == hoy)
        )).scalar_one()

        # Última actividad (último check-in en cualquier fecha)
        ultima_fecha = (await db.execute(
            select(sqlfunc.max(Checkin.fecha))
            .join(Jugador, Checkin.jugador_id == Jugador.id)
            .join(Categoria, Jugador.categoria_id == Categoria.id)
            .where(Categoria.club_id == club.id)
        )).scalar_one()

        # Staff Telegram vinculado
        staff_total = (await db.execute(
            select(sqlfunc.count(Staff.id))
            .where(Staff.club_id == club.id, Staff.activo == True)  # noqa: E712
        )).scalar_one()
        staff_tg = (await db.execute(
            select(sqlfunc.count(Staff.id))
            .where(Staff.club_id == club.id, Staff.activo == True, Staff.telegram_chat_id.isnot(None))  # noqa: E712
        )).scalar_one()

        # Alertas fallidas últimos 7 días
        alertas_fallidas = (await db.execute(
            select(sqlfunc.count(AlertaLog.id))
            .where(
                AlertaLog.categoria_id.in_(
                    select(Categoria.id).where(Categoria.club_id == club.id)
                ),
                AlertaLog.estado_envio == "failed",
                AlertaLog.created_at >= datetime.combine(hace7, dtime.min),
            )
        )).scalar_one()

        # Actividad últimos 7 días
        checkins_7d = (await db.execute(
            select(sqlfunc.count(Checkin.id))
            .join(Jugador, Checkin.jugador_id == Jugador.id)
            .join(Categoria, Jugador.categoria_id == Categoria.id)
            .where(Categoria.club_id == club.id, Checkin.fecha >= hace7)
        )).scalar_one()

        dias_inactivo = (hoy - ultima_fecha).days if ultima_fecha else None

        filas.append({
            "club": club,
            "n_jugadores": n_jugadores,
            "n_cats": n_cats,
            "checkins_hoy": checkins_hoy,
            "checkouts_hoy": checkouts_hoy,
            "ultima_fecha": ultima_fecha,
            "dias_inactivo": dias_inactivo,
            "staff_tg": staff_tg,
            "staff_total": staff_total,
            "alertas_fallidas": alertas_fallidas,
            "checkins_7d": checkins_7d,
        })

    return templates.TemplateResponse(request, "admin/clubes.html", {
        "filas": filas,
        "hoy": hoy,
    })


# ---------- Vista del día ----------

@router.get("/{club_slug}")
async def vista_dia(request: Request, club_slug: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    hoy = datetime.now(ZoneInfo(club.timezone)).date()

    categorias = (await db.execute(
        select(Categoria).where(Categoria.club_id == club.id, Categoria.activo == True)  # noqa: E712
        .order_by(Categoria.nombre)
    )).scalars().all()

    if not categorias:
        # Club recién registrado: guía de primeros pasos en vez de una vista vacía
        return templates.TemplateResponse(request, "admin/inicio.html", {"club": club})

    bloques = []
    for cat in categorias:
        jugadores = (await db.execute(
            select(Jugador).where(Jugador.categoria_id == cat.id, Jugador.activo == True)  # noqa: E712
            .order_by(Jugador.apellido, Jugador.nombre)
        )).scalars().all()
        checkins = {c.jugador_id: c for c in (await db.execute(
            select(Checkin).join(Jugador, Checkin.jugador_id == Jugador.id)
            .where(Jugador.categoria_id == cat.id, Checkin.fecha == hoy)
        )).scalars().all()}
        checkouts = {c.jugador_id: c for c in (await db.execute(
            select(Checkout).join(Jugador, Checkout.jugador_id == Jugador.id)
            .where(Jugador.categoria_id == cat.id, Checkout.fecha == hoy)
        )).scalars().all()}
        sesion = (await db.execute(
            select(SesionDia).where(SesionDia.categoria_id == cat.id, SesionDia.fecha == hoy)
        )).scalar_one_or_none()

        filas = []
        for j in jugadores:
            ci, co = checkins.get(j.id), checkouts.get(j.id)
            filas.append({
                "jugador": j,
                "checkin": ci,
                "checkout": co,
                "molestia": bool((ci and ci.molestia_previa) or (co and co.molestia_nueva)),
            })
        bloques.append({"categoria": cat, "filas": filas, "sesion": sesion})

    return templates.TemplateResponse(request, "admin/dia.html", {
        "club": club, "hoy": hoy, "bloques": bloques,
    })


# ---------- Reenvíos manuales ----------

@router.post("/{club_slug}/categorias/{categoria_id}/reenviar-semaforo")
async def reenviar_semaforo(club_slug: str, categoria_id: int, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    categoria = await _get_categoria(db, club.id, categoria_id)
    hoy = datetime.now(ZoneInfo(club.timezone)).date()

    await db.execute(
        update(SesionDia)
        .where(SesionDia.categoria_id == categoria.id, SesionDia.fecha == hoy)
        .values(semaforo_enviado=False)
    )
    await semaforo_svc.enviar_semaforo(db, categoria, hoy, forzado=True)
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}", status_code=303)


@router.post("/{club_slug}/categorias/{categoria_id}/reenviar-resumen")
async def reenviar_resumen(club_slug: str, categoria_id: int, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    categoria = await _get_categoria(db, club.id, categoria_id)
    hoy = datetime.now(ZoneInfo(club.timezone)).date()

    await db.execute(
        update(SesionDia)
        .where(SesionDia.categoria_id == categoria.id, SesionDia.fecha == hoy)
        .values(resumen_enviado=False)
    )
    await resumen_svc.enviar_resumen(db, categoria, hoy)
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}", status_code=303)


# ---------- Jugadores ----------

@router.get("/{club_slug}/jugadores")
async def jugadores_page(request: Request, club_slug: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    categorias = await _categorias_de(db, club.id)
    jugadores = (await db.execute(
        select(Jugador, Categoria.nombre.label("categoria_nombre"))
        .join(Categoria, Jugador.categoria_id == Categoria.id)
        .where(Categoria.club_id == club.id)
        .order_by(Categoria.nombre, Jugador.apellido)
    )).all()
    return templates.TemplateResponse(request, "admin/jugadores.html", {
        "club": club, "categorias": categorias, "jugadores": jugadores,
    })


@router.post("/{club_slug}/jugadores")
async def crear_jugador(
    club_slug: str,
    nombre: str = Form(...),
    apellido: str = Form(...),
    categoria_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    await _get_categoria(db, club.id, categoria_id)
    db.add(Jugador(categoria_id=categoria_id, nombre=nombre.strip(), apellido=apellido.strip()))
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/jugadores", status_code=303)


@router.post("/{club_slug}/jugadores/masivo")
async def crear_jugadores_masivo(
    club_slug: str,
    categoria_id: int = Form(...),
    lista: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Alta masiva: una línea por jugador, "Nombre Apellido(s)"."""
    club = await _get_club(db, club_slug)
    await _get_categoria(db, club.id, categoria_id)
    for linea in lista.splitlines()[:200]:
        partes = linea.strip().split(maxsplit=1)
        if not partes:
            continue
        nombre = partes[0]
        apellido = partes[1] if len(partes) > 1 else ""
        db.add(Jugador(categoria_id=categoria_id, nombre=nombre, apellido=apellido))
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/jugadores", status_code=303)


@router.post("/{club_slug}/jugadores/{jugador_id}/editar")
async def editar_jugador(
    club_slug: str,
    jugador_id: int,
    nombre: str = Form(...),
    apellido: str = Form(...),
    categoria_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    jugador = await _get_jugador(db, club.id, jugador_id)
    await _get_categoria(db, club.id, categoria_id)
    jugador.nombre, jugador.apellido, jugador.categoria_id = nombre.strip(), apellido.strip(), categoria_id
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/jugadores", status_code=303)


@router.post("/{club_slug}/jugadores/{jugador_id}/toggle")
async def toggle_jugador(club_slug: str, jugador_id: int, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    jugador = await _get_jugador(db, club.id, jugador_id)
    jugador.activo = not jugador.activo
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/jugadores", status_code=303)


# ---------- Staff ----------

@router.get("/{club_slug}/staff")
async def staff_page(request: Request, club_slug: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    staff = (await db.execute(
        select(Staff).where(Staff.club_id == club.id).order_by(Staff.nombre)
    )).scalars().all()
    return templates.TemplateResponse(request, "admin/staff.html", {"club": club, "staff": staff})


@router.post("/{club_slug}/staff")
async def crear_staff(
    club_slug: str,
    nombre: str = Form(...),
    telefono: str = Form(...),
    rol: str = Form(...),
    recibe_alertas: bool = Form(False),
    recibe_resumen: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    db.add(Staff(
        club_id=club.id, nombre=nombre.strip(), telefono_whatsapp=telefono.strip(),
        rol=rol, recibe_alertas=recibe_alertas, recibe_resumen=recibe_resumen,
    ))
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/staff", status_code=303)


@router.post("/{club_slug}/staff/{staff_id}/toggle")
async def toggle_staff(club_slug: str, staff_id: int, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    miembro = (await db.execute(
        select(Staff).where(Staff.id == staff_id, Staff.club_id == club.id)
    )).scalar_one_or_none()
    if not miembro:
        raise HTTPException(404)
    miembro.activo = not miembro.activo
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/staff", status_code=303)


# ---------- Categorías ----------

@router.get("/{club_slug}/categorias")
async def categorias_page(request: Request, club_slug: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    categorias = await _categorias_de(db, club.id, solo_activas=False)
    return templates.TemplateResponse(request, "admin/categorias.html", {
        "club": club, "categorias": categorias, "dias_nombres": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
    })


@router.post("/{club_slug}/categorias")
async def crear_categoria(
    request: Request,
    club_slug: str,
    nombre: str = Form(...),
    hora_inicio: str = Form(...),
    hora_fin: str = Form(...),
    hora_resumen: str = Form("19:00"),
    min_checkins_semaforo: int = Form(10),
    umbral_alerta_carga: int = Form(3500),
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    form = await request.form()
    dias = [int(d) for d in form.getlist("dias")]
    db.add(Categoria(
        club_id=club.id, nombre=nombre.strip(),
        hora_inicio=hora_inicio, hora_fin=hora_fin, hora_resumen=hora_resumen,
        dias_entrenamiento=dias or [0, 1, 2, 3, 4],
        min_checkins_semaforo=min_checkins_semaforo,
        umbral_alerta_carga=umbral_alerta_carga,
    ))
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/categorias", status_code=303)


@router.post("/{club_slug}/categorias/{categoria_id}/editar")
async def editar_categoria(
    request: Request,
    club_slug: str,
    categoria_id: int,
    hora_inicio: str = Form(...),
    hora_fin: str = Form(...),
    hora_resumen: str = Form(...),
    min_checkins_semaforo: int = Form(...),
    umbral_alerta_carga: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    categoria = await _get_categoria(db, club.id, categoria_id)
    form = await request.form()
    dias = [int(d) for d in form.getlist("dias")]
    categoria.hora_inicio = hora_inicio
    categoria.hora_fin = hora_fin
    categoria.hora_resumen = hora_resumen
    categoria.min_checkins_semaforo = min_checkins_semaforo
    categoria.umbral_alerta_carga = umbral_alerta_carga
    if dias:
        categoria.dias_entrenamiento = dias
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/categorias", status_code=303)


# ---------- Recordatorios ----------

@router.get("/{club_slug}/recordatorios")
async def recordatorios_page(request: Request, club_slug: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    categorias = await _categorias_de(db, club.id)
    recordatorios = (await db.execute(
        select(Recordatorio, Categoria.nombre.label("categoria_nombre"))
        .join(Categoria, Recordatorio.categoria_id == Categoria.id)
        .where(Categoria.club_id == club.id)
        .order_by(Categoria.nombre)
    )).all()
    return templates.TemplateResponse(request, "admin/recordatorios.html", {
        "club": club, "categorias": categorias, "recordatorios": recordatorios,
    })


@router.post("/{club_slug}/recordatorios")
async def crear_recordatorio(
    club_slug: str,
    categoria_id: int = Form(...),
    nombre: str = Form(...),
    mensaje: str = Form(...),
    hora: Optional[str] = Form(None),
    minutos_antes: Optional[int] = Form(None),
    condicion_min_checkins: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    club = await _get_club(db, club_slug)
    await _get_categoria(db, club.id, categoria_id)
    if not hora and minutos_antes is None:
        raise HTTPException(422, "Debe indicar hora fija o minutos antes del entrenamiento")
    db.add(Recordatorio(
        categoria_id=categoria_id, nombre=nombre.strip(), mensaje=mensaje.strip(),
        hora=hora or None, minutos_antes=minutos_antes,
        condicion_min_checkins=condicion_min_checkins,
    ))
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/recordatorios", status_code=303)


@router.post("/{club_slug}/recordatorios/{recordatorio_id}/toggle")
async def toggle_recordatorio(club_slug: str, recordatorio_id: int, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    rec = (await db.execute(
        select(Recordatorio)
        .join(Categoria, Recordatorio.categoria_id == Categoria.id)
        .where(Recordatorio.id == recordatorio_id, Categoria.club_id == club.id)
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404)
    rec.activo = not rec.activo
    await db.commit()
    return RedirectResponse(f"/admin/{club_slug}/recordatorios", status_code=303)


# ---------- Log de alertas ----------

@router.get("/{club_slug}/alertas")
async def alertas_page(request: Request, club_slug: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club(db, club_slug)
    alertas = (await db.execute(
        select(AlertaLog, Categoria.nombre.label("categoria_nombre"))
        .join(Categoria, AlertaLog.categoria_id == Categoria.id)
        .where(Categoria.club_id == club.id)
        .order_by(AlertaLog.id.desc())
        .limit(100)
    )).all()
    return templates.TemplateResponse(request, "admin/alertas.html", {"club": club, "alertas": alertas})


# ---------- Helpers ----------

async def _get_club(db: AsyncSession, slug: str) -> Club:
    club = (await db.execute(select(Club).where(Club.slug == slug))).scalar_one_or_none()
    if not club:
        raise HTTPException(404, "Club no encontrado")
    return club


async def _get_categoria(db: AsyncSession, club_id: int, categoria_id: int) -> Categoria:
    cat = (await db.execute(
        select(Categoria).where(Categoria.id == categoria_id, Categoria.club_id == club_id)
    )).scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Categoría no encontrada")
    return cat


async def _get_jugador(db: AsyncSession, club_id: int, jugador_id: int) -> Jugador:
    jugador = (await db.execute(
        select(Jugador)
        .join(Categoria, Jugador.categoria_id == Categoria.id)
        .where(Jugador.id == jugador_id, Categoria.club_id == club_id)
    )).scalar_one_or_none()
    if not jugador:
        raise HTTPException(404, "Jugador no encontrado")
    return jugador


async def _categorias_de(db: AsyncSession, club_id: int, solo_activas: bool = True) -> list[Categoria]:
    query = select(Categoria).where(Categoria.club_id == club_id).order_by(Categoria.nombre)
    if solo_activas:
        query = query.where(Categoria.activo == True)  # noqa: E712
    return (await db.execute(query)).scalars().all()
