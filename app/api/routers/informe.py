from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import Categoria, Checkin, Checkout, Club, Jugador

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_ESTADOS = [
    (5.5, "verde"),
    (4.5, "amarillo"),
    (3.5, "naranja"),
    (0.0, "rojo"),
]
_ORDEN = {"rojo": 0, "naranja": 1, "amarillo": 2, "verde": 3, "sin_datos": 4}


def _bienestar(c: Checkin):
    if any(getattr(c, f) is None for f in ("sueno", "energia", "dolor_pre", "estres")):
        return None
    return (c.sueno + c.energia + (8 - c.dolor_pre) + (8 - c.estres)) / 4


def _estado(b):
    if b is None:
        return "sin_datos"
    for umbral, nombre in _ESTADOS:
        if b >= umbral:
            return nombre
    return "rojo"


@router.get("/r/{categoria_id}/{fecha_str}", response_class=HTMLResponse)
async def informe_diario(
    request: Request,
    categoria_id: int,
    fecha_str: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida")

    categoria = await db.get(Categoria, categoria_id)
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    club = await db.get(Club, categoria.club_id)

    jugadores = (await db.execute(
        select(Jugador)
        .where(Jugador.categoria_id == categoria_id, Jugador.activo == True)  # noqa: E712
        .order_by(Jugador.apellido, Jugador.nombre)
    )).scalars().all()

    # Checkins con asistencia
    ci_rows = (await db.execute(
        select(Checkin, Jugador)
        .join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria_id, Checkin.fecha == fecha)
    )).all()

    asistentes = {c.jugador_id: (c, j) for c, j in ci_rows if c.asistencia}
    inasistentes = {c.jugador_id: (c, j) for c, j in ci_rows if not c.asistencia}
    sin_registro = [j for j in jugadores if j.id not in asistentes and j.id not in inasistentes]

    # Checkouts del día
    co_rows = (await db.execute(
        select(Checkout)
        .join(Jugador, Checkout.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria_id, Checkout.fecha == fecha)
    )).scalars().all()
    checkout_por_jugador = {co.jugador_id: co for co in co_rows}

    # Construir cards de bienestar
    registros = []
    for jugador_id, (ci, jug) in asistentes.items():
        b = _bienestar(ci)
        co = checkout_por_jugador.get(jugador_id)
        registros.append({
            "nombre": f"{jug.nombre} {jug.apellido}",
            "bienestar": round(b, 1) if b is not None else None,
            "estado": _estado(b),
            "sueno": ci.sueno,
            "energia": ci.energia,
            "animo": ci.animo,
            "dolor": ci.dolor_pre,
            "estres": ci.estres,
            "hora_inicio": ci.hora_inicio_declarada,
            "rpe": co.rpe if co else None,
            "duracion": co.duracion_min if co else None,
            "carga": co.carga if co else None,
        })
    registros.sort(key=lambda r: (_ORDEN[r["estado"]], r["bienestar"] or 99))

    inasistencias = [
        {"nombre": f"{j.nombre} {j.apellido}", "motivo": c.motivo_inasistencia or "—"}
        for _, (c, j) in inasistentes.items()
    ]

    pendientes = [{"nombre": f"{j.nombre} {j.apellido}"} for j in sin_registro]

    # Checkout summary: who checked in but didn't checkout yet
    sin_checkout = [
        {"nombre": f"{jug.nombre} {jug.apellido}"}
        for jugador_id, (ci, jug) in asistentes.items()
        if jugador_id not in checkout_por_jugador
    ]
    con_checkout = [
        {
            "nombre": f"{jug.nombre} {jug.apellido}",
            "rpe": co.rpe,
            "duracion": co.duracion_min,
            "carga": co.carga,
        }
        for jugador_id, (ci, jug) in asistentes.items()
        if (co := checkout_por_jugador.get(jugador_id))
    ]

    # Conteo por estado
    conteo = {"verde": 0, "amarillo": 0, "naranja": 0, "rojo": 0, "sin_datos": 0}
    for r in registros:
        conteo[r["estado"]] += 1

    # Historial últimos 7 días (para sparkline)
    hace_7 = fecha - timedelta(days=6)
    historial_rows = (await db.execute(
        select(Checkin)
        .join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(
            Jugador.categoria_id == categoria_id,
            Checkin.fecha >= hace_7,
            Checkin.fecha <= fecha,
            Checkin.asistencia == True,  # noqa: E712
        )
    )).scalars().all()

    asistencia_7d = {}
    for ci in historial_rows:
        d = ci.fecha.isoformat()
        asistencia_7d[d] = asistencia_7d.get(d, 0) + 1

    dias_7 = [(hace_7 + timedelta(days=i)).isoformat() for i in range(7)]

    from app.config import settings
    base = settings.base_url.rstrip("/") if settings.base_url else ""
    checkin_url = f"{base}/f/{club.slug}/{categoria.nombre}"

    return templates.TemplateResponse("informe.html", {
        "request": request,
        "categoria": categoria,
        "club": club,
        "fecha": fecha,
        "fecha_str": fecha_str,
        "registros": registros,
        "pendientes": pendientes,
        "inasistencias": inasistencias,
        "sin_checkout": sin_checkout,
        "con_checkout": con_checkout,
        "total_activos": len(jugadores),
        "conteo": conteo,
        "asistencia_7d": [asistencia_7d.get(d, 0) for d in dias_7],
        "dias_7_labels": [d[5:] for d in dias_7],  # MM-DD
        "checkin_url": checkin_url,
    })
