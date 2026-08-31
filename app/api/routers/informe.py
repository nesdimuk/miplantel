from datetime import date, timedelta
from statistics import mean

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
    (5.0, "verde"),
    (3.5, "amarillo"),
    (0.0, "rojo"),
]
_ORDEN = {"rojo": 0, "amarillo": 1, "verde": 2, "sin_datos": 3}


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
            "molestia_previa": ci.molestia_previa,
            "molestia_zona": ci.molestia_zona,
            "molestia_severidad": ci.molestia_severidad,
            "rpe": co.rpe if co else None,
            "duracion": co.duracion_min if co else None,
            "carga": co.carga if co else None,
        })
    registros.sort(key=lambda r: (_ORDEN[r["estado"]], r["bienestar"] or 99))

    # Construir lista de urgentes: molestia bloqueante + inasistencias
    urgentes = []
    for r in registros:
        if r["molestia_previa"] and r["molestia_severidad"] == "bloqueante":
            zona = r["molestia_zona"] or "zona no indicada"
            urgentes.append({"nombre": r["nombre"], "tags": [f"🚨 Molestia bloqueante — {zona}"]})
    for c, j in inasistentes.values():
        urgentes.append({"nombre": f"{j.nombre} {j.apellido}", "tags": ["⚠️ Inasistencia"]})

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
    conteo = {"verde": 0, "amarillo": 0, "rojo": 0, "sin_datos": 0}
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
        "urgentes": urgentes,
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


@router.get("/api/sin-checkout/{categoria_id}/{fecha_str}")
async def sin_checkout_live(
    categoria_id: int,
    fecha_str: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida")

    jugadores = {j.id: j for j in (await db.execute(
        select(Jugador).where(Jugador.categoria_id == categoria_id, Jugador.activo == True)  # noqa: E712
    )).scalars().all()}

    asistentes_ids = {c.jugador_id for c in (await db.execute(
        select(Checkin).join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria_id, Checkin.fecha == fecha, Checkin.asistencia == True)  # noqa: E712
    )).scalars().all()}

    checkout_ids = {co.jugador_id for co in (await db.execute(
        select(Checkout).join(Jugador, Checkout.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria_id, Checkout.fecha == fecha)
    )).scalars().all()}

    pendientes = [
        f"{jugadores[jid].nombre} {jugadores[jid].apellido}"
        for jid in asistentes_ids
        if jid not in checkout_ids and jid in jugadores
    ]
    pendientes.sort()
    return {"pendientes": pendientes}


@router.get("/r/{categoria_id}/{fecha_str}/post", response_class=HTMLResponse)
async def informe_post(
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

    jugadores = {j.id: j for j in (await db.execute(
        select(Jugador).where(Jugador.categoria_id == categoria_id, Jugador.activo == True)  # noqa: E712
    )).scalars().all()}

    ci_rows = (await db.execute(
        select(Checkin).join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria_id, Checkin.fecha == fecha, Checkin.asistencia == True)  # noqa: E712
    )).scalars().all()
    asistentes_ids = {c.jugador_id for c in ci_rows}

    co_rows = (await db.execute(
        select(Checkout).join(Jugador, Checkout.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria_id, Checkout.fecha == fecha)
    )).scalars().all()
    checkout_por_jugador = {co.jugador_id: co for co in co_rows}

    con_checkout = []
    for jid in asistentes_ids:
        co = checkout_por_jugador.get(jid)
        if co:
            j = jugadores.get(jid)
            con_checkout.append({
                "nombre": f"{j.nombre} {j.apellido}",
                "rpe": co.rpe,
                "duracion": co.duracion_min,
                "carga": co.carga,
                "fisico": co.fisico_post,
                "rendimiento": co.rendimiento,
                "molestia_nueva": co.molestia_nueva,
                "molestia_zona": co.molestia_zona,
                "molestia_severidad": co.molestia_severidad,
            })
    con_checkout.sort(key=lambda r: r["nombre"])

    sin_checkout = [
        {"nombre": f"{jugadores[jid].nombre} {jugadores[jid].apellido}"}
        for jid in asistentes_ids if jid not in checkout_por_jugador and jid in jugadores
    ]

    sin_checkin = [
        {"nombre": f"{j.nombre} {j.apellido}"}
        for jid, j in jugadores.items() if jid not in asistentes_ids
    ]
    sin_checkin.sort(key=lambda x: x["nombre"])

    rpes = [r["rpe"] for r in con_checkout if r["rpe"] is not None]
    rpe_promedio = round(mean(rpes), 1) if rpes else None
    cargas = [r["carga"] for r in con_checkout if r["carga"] is not None]
    carga_promedio = round(mean(cargas)) if cargas else None

    molestias_post = [r for r in con_checkout if r["molestia_nueva"]]

    from app.config import settings
    base = settings.base_url.rstrip("/") if settings.base_url else ""
    form_url = f"{base}/f/{club.slug}/{categoria.nombre}"

    return templates.TemplateResponse("informe_post.html", {
        "request": request,
        "categoria": categoria,
        "club": club,
        "fecha": fecha,
        "con_checkout": con_checkout,
        "sin_checkout": sin_checkout,
        "sin_checkin": sin_checkin,
        "total_asistentes": len(asistentes_ids),
        "rpe_promedio": rpe_promedio,
        "carga_promedio": carga_promedio,
        "molestias_post": molestias_post,
        "checkout_url": form_url,
        "checkin_url": form_url,
    })


@router.get("/r/{categoria_id}/{fecha_str}/dia", response_class=HTMLResponse)
async def informe_dia(
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
        select(Jugador).where(Jugador.categoria_id == categoria_id, Jugador.activo == True)  # noqa: E712
    )).scalars().all()
    total_activos = len(jugadores)

    ci_rows = (await db.execute(
        select(Checkin, Jugador).join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria_id, Checkin.fecha == fecha)
    )).all()

    asistentes = [(c, j) for c, j in ci_rows if c.asistencia]
    inasistentes = [(c, j) for c, j in ci_rows if not c.asistencia]

    co_rows = (await db.execute(
        select(Checkout).join(Jugador, Checkout.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria_id, Checkout.fecha == fecha)
    )).scalars().all()

    # Bienestar promedio
    scores = []
    conteo = {"verde": 0, "amarillo": 0, "rojo": 0}
    molestias_pre = []
    for ci, jug in asistentes:
        b = _bienestar(ci)
        if b is not None:
            scores.append(b)
            estado = _estado(b)
            if estado in conteo:
                conteo[estado] += 1
        if ci.molestia_previa:
            molestias_pre.append({
                "nombre": f"{jug.nombre} {jug.apellido}",
                "zona": ci.molestia_zona or "—",
                "severidad": ci.molestia_severidad or "—",
                "momento": "pre-entreno",
            })

    bienestar_promedio = round(mean(scores), 1) if scores else None

    checkout_por_jugador = {co.jugador_id: co for co in co_rows}
    molestias_post = []
    rpes = []
    cargas = []
    for co in co_rows:
        if co.rpe is not None:
            rpes.append(co.rpe)
        if co.carga is not None:
            cargas.append(co.carga)
        if co.molestia_nueva:
            j = next((j for _, j in asistentes if j.id == co.jugador_id), None)
            nombre = f"{j.nombre} {j.apellido}" if j else f"Jugador {co.jugador_id}"
            molestias_post.append({
                "nombre": nombre,
                "zona": co.molestia_zona or "—",
                "severidad": co.molestia_severidad or "—",
                "momento": "post-entreno",
            })

    # Ficha individual por jugador (para expandible)
    _ORDEN_DIA = {"rojo": 0, "amarillo": 1, "verde": 2, "sin_datos": 3}
    fichas = []
    for ci, jug in asistentes:
        b = _bienestar(ci)
        est = _estado(b)
        co = checkout_por_jugador.get(jug.id)
        fichas.append({
            "nombre": f"{jug.nombre} {jug.apellido}",
            "estado": est,
            "bienestar": round(b, 1) if b is not None else None,
            "sueno": ci.sueno,
            "energia": ci.energia,
            "estres_ef": (8 - ci.estres) if ci.estres is not None else None,
            "dolor_ef": (8 - ci.dolor_pre) if ci.dolor_pre is not None else None,
            "animo": ci.animo,
            "molestia_previa": ci.molestia_previa,
            "molestia_zona_pre": ci.molestia_zona,
            "molestia_sev_pre": ci.molestia_severidad,
            "rpe": co.rpe if co else None,
            "carga": co.carga if co else None,
            "molestia_nueva": co.molestia_nueva if co else None,
            "molestia_zona_post": co.molestia_zona if co else None,
            "molestia_sev_post": co.molestia_severidad if co else None,
        })
    fichas.sort(key=lambda f: (_ORDEN_DIA[f["estado"]], f["bienestar"] or 99))

    from app.config import settings
    base = settings.base_url.rstrip("/") if settings.base_url else ""
    checkin_url_dia = f"{base}/f/{club.slug}/{categoria.nombre}"

    return templates.TemplateResponse("informe_dia.html", {
        "request": request,
        "categoria": categoria,
        "club": club,
        "fecha": fecha,
        "total_activos": total_activos,
        "total_asistentes": len(asistentes),
        "total_inasistentes": len(inasistentes),
        "total_checkouts": len(co_rows),
        "bienestar_promedio": bienestar_promedio,
        "conteo": conteo,
        "rpe_promedio": round(mean(rpes), 1) if rpes else None,
        "carga_promedio": round(mean(cargas)) if cargas else None,
        "carga_total": sum(cargas) if cargas else None,
        "molestias": molestias_pre + molestias_post,
        "inasistentes": [{"nombre": f"{j.nombre} {j.apellido}", "motivo": c.motivo_inasistencia or "—"} for c, j in inasistentes],
        "fichas": fichas,
        "checkin_url": checkin_url_dia,
    })
