"""Read-model for the club dashboards: adherence, Hooper averages, RPE, risk flags, insights."""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Categoria, Checkin, Checkout, Jugador
from app.services import carga as carga_svc

RANGO_DIAS = 28


async def datos_categoria(db: AsyncSession, categoria: Categoria, hasta: date) -> dict:
    desde = hasta - timedelta(days=RANGO_DIAS - 1)

    jugadores = (await db.execute(
        select(Jugador).where(Jugador.categoria_id == categoria.id, Jugador.activo == True)  # noqa: E712
        .order_by(Jugador.apellido, Jugador.nombre)
    )).scalars().all()

    checkins = (await db.execute(
        select(Checkin).join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria.id, Checkin.fecha.between(desde, hasta))
    )).scalars().all()

    checkouts = (await db.execute(
        select(Checkout).join(Jugador, Checkout.jugador_id == Jugador.id)
        .where(Jugador.categoria_id == categoria.id, Checkout.fecha.between(desde, hasta))
    )).scalars().all()

    dias_activos = sorted({c.fecha for c in checkins})
    asistencias = [c for c in checkins if c.asistencia]
    hace7 = hasta - timedelta(days=6)

    # ---- Por jugador ----
    filas = []
    for j in jugadores:
        mis_checkins = [c for c in checkins if c.jugador_id == j.id]
        mis_asistencias = [c for c in mis_checkins if c.asistencia]
        mis_checkouts = [c for c in checkouts if c.jugador_id == j.id]
        molestias = sum(1 for c in mis_asistencias if c.molestia_previa) + \
                    sum(1 for c in mis_checkouts if c.molestia_nueva)

        aguda = await carga_svc.carga_aguda(db, j.id, hasta)
        acwr = await carga_svc.calcular_acwr(db, j.id, hasta)

        ultimos3 = sorted(mis_asistencias, key=lambda c: c.fecha, reverse=True)[:3]
        avg_sueno3 = round(sum(c.sueno for c in ultimos3) / len(ultimos3), 1) if ultimos3 else None
        avg_animo3 = round(sum(c.animo for c in ultimos3) / len(ultimos3), 1) if ultimos3 else None

        riesgo = []
        if avg_sueno3 is not None and avg_sueno3 <= 2:
            riesgo.append("sueño bajo")
        if avg_animo3 is not None and avg_animo3 <= 2:
            riesgo.append("ánimo bajo")
        if aguda > categoria.umbral_alerta_carga:
            riesgo.append("carga alta")
        if acwr is not None and acwr > 1.5:
            riesgo.append(f"ACWR alto {acwr}")
        # ACWR bajo también es riesgo: jugador desentrenado que al retomar carga se expone
        if acwr is not None and acwr < 0.8:
            riesgo.append(f"ACWR bajo {acwr}")
        if molestias >= 2:
            riesgo.append(f"{molestias} molestias")

        rpe_7d_vals = [c.rpe for c in mis_checkouts if c.fecha >= hace7]
        rpe_28d_vals = [c.rpe for c in mis_checkouts]

        filas.append({
            "jugador": j,
            "registros": len(mis_checkins),
            "asistencias": len(mis_asistencias),
            "checkouts": len(mis_checkouts),
            "adhesion": round(len(mis_checkins) / len(dias_activos) * 100) if dias_activos else 0,
            "proceso": round(len(mis_checkouts) / len(mis_asistencias) * 100) if mis_asistencias else 0,
            "molestias": molestias,
            "carga_aguda": aguda,
            "acwr": acwr,
            "riesgo": riesgo,
            # Sin check-outs no hay datos de carga: no se puede afirmar que el jugador está OK
            "sin_carga": len(mis_checkouts) == 0,
            "rpe_7d": round(sum(rpe_7d_vals) / len(rpe_7d_vals), 1) if rpe_7d_vals else None,
            "rpe_28d": round(sum(rpe_28d_vals) / len(rpe_28d_vals), 1) if rpe_28d_vals else None,
        })

    # ---- Gráfica de microciclo: todas las variables × semana × día-de-semana ----
    def _iso_key(fecha):
        y, w, _ = fecha.isocalendar()
        return (y, w)

    def _agrupar(registros, val_fn, semana_keys):
        """→ {semana_idx: {dow: [valores]}}"""
        sidx = {k: i for i, k in enumerate(semana_keys)}
        agr: dict = defaultdict(lambda: defaultdict(list))
        for r in registros:
            k = _iso_key(r.fecha)
            if k in sidx:
                v = val_fn(r)
                if v is not None:
                    agr[sidx[k]][r.fecha.weekday()].append(v)
        return agr

    def _matrix(agr, n_sem):
        """→ lista de n_sem listas de 7 valores (o None)"""
        return [
            [
                round(sum(agr[si][d]) / len(agr[si][d]), 1) if d in agr.get(si, {}) else None
                for d in range(7)
            ]
            for si in range(n_sem)
        ]

    # Semanas presentes (union de checkins y checkouts)
    semana_keys = sorted(
        {_iso_key(c.fecha) for c in checkouts} | {_iso_key(c.fecha) for c in asistencias}
    )
    n_sem = len(semana_keys)
    semana_labels = [f"S{i+1}" for i in range(n_sem)]

    def _mc_vars(c_outs, c_ins):
        return {
            "rpe":     _matrix(_agrupar(c_outs, lambda c: c.rpe,       semana_keys), n_sem),
            "carga":   _matrix(_agrupar(c_outs, lambda c: c.carga,     semana_keys), n_sem),
            "sueno":   _matrix(_agrupar(c_ins,  lambda c: c.sueno,     semana_keys), n_sem),
            "energia": _matrix(_agrupar(c_ins,  lambda c: c.energia,   semana_keys), n_sem),
            "animo":   _matrix(_agrupar(c_ins,  lambda c: c.animo,     semana_keys), n_sem),
            "dolor":   _matrix(_agrupar(c_ins,  lambda c: c.dolor_pre, semana_keys), n_sem),
        }

    mc_club = _mc_vars(checkouts, asistencias)
    mc_jugadores = [
        {
            "id": j.id,
            "nombre": f"{j.nombre} {j.apellido}",
            "vars": _mc_vars(
                [c for c in checkouts  if c.jugador_id == j.id],
                [c for c in asistencias if c.jugador_id == j.id],
            ),
        }
        for j in jugadores
    ]

    # ---- RPE promedio por sesión (línea de tiempo, vista secundaria) ----
    rpe_dia_raw: dict = defaultdict(list)
    for c in checkouts:
        rpe_dia_raw[c.fecha].append(c.rpe)
    rpe_por_dia = [
        {
            "fecha": k,
            "label": f"{['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'][k.weekday()]} {k.strftime('%d/%m')}",
            "rpe": round(sum(v) / len(v), 1),
            "n": len(v),
            "en_7d": k >= hace7,
        }
        for k, v in sorted(rpe_dia_raw.items())
    ]
    max_rpe_dia = max((d["rpe"] for d in rpe_por_dia), default=10)

    # ---- Plantel: promedios Hooper (últimos 7 días) ----
    recientes = [c for c in asistencias if c.fecha >= hace7]
    def _avg(attr):
        vals = [getattr(c, attr) for c in recientes if getattr(c, attr) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None
    hooper = {
        "sueno": _avg("sueno"), "energia": _avg("energia"),
        "animo": _avg("animo"), "dolor": _avg("dolor_pre"),
        "n": len(recientes),
    }

    # ---- Tendencia semanal (bienestar compuesto) ----
    def _bienestar(cs):
        vals = [(c.sueno + c.energia + c.animo + (8 - c.dolor_pre)) / 4 for c in cs
                if None not in (c.sueno, c.energia, c.animo, c.dolor_pre)]
        return round(sum(vals) / len(vals), 2) if vals else None
    semana_actual = _bienestar([c for c in asistencias if c.fecha >= hace7])
    semana_previa = _bienestar([c for c in asistencias if hace7 - timedelta(days=7) <= c.fecha < hace7])

    # ---- Distribución RPE ----
    rpe_dist = {v: 0 for v in range(11)}
    for c in checkouts:
        rpe_dist[c.rpe] += 1
    max_rpe = max(rpe_dist.values()) or 1

    # ---- Insights automáticos ----
    insights = []
    if semana_actual is not None and semana_previa is not None:
        delta = round(semana_actual - semana_previa, 2)
        flecha = "📈 mejoró" if delta > 0.2 else ("📉 bajó" if delta < -0.2 else "➡️ se mantiene")
        insights.append(f"El bienestar del plantel {flecha} respecto a la semana anterior ({semana_previa} → {semana_actual}).")
    en_riesgo = [f for f in filas if f["riesgo"]]
    if en_riesgo:
        nombres = ", ".join(f"{f['jugador'].nombre} {f['jugador'].apellido}" for f in en_riesgo[:5])
        insights.append(f"⚠️ {len(en_riesgo)} jugador(es) con señales de riesgo: {nombres}.")
    if filas and dias_activos:
        baja = [f for f in filas if f["adhesion"] < 50]
        if baja:
            insights.append(f"📋 {len(baja)} jugador(es) con adhesión bajo 50% en los últimos {len(dias_activos)} días activos.")
        top = max(filas, key=lambda f: f["registros"])
        if top["registros"] > 0:
            insights.append(f"🏆 Mayor adhesión: {top['jugador'].nombre} {top['jugador'].apellido} ({top['registros']} registros).")
    procesos = [f["proceso"] for f in filas if f["asistencias"] > 0]
    if procesos:
        insights.append(f"🔄 Proceso completo (check-in + check-out): {round(sum(procesos) / len(procesos))}% promedio del plantel.")
    if not insights:
        insights.append("Aún no hay datos suficientes para generar insights.")

    return {
        "desde": desde,
        "hasta": hasta,
        "dias_activos": len(dias_activos),
        "filas": filas,
        "hooper": hooper,
        "semana_actual": semana_actual,
        "semana_previa": semana_previa,
        "rpe_dist": rpe_dist,
        "max_rpe": max_rpe,
        "rpe_por_dia": rpe_por_dia,
        "max_rpe_dia": max_rpe_dia,
        "mc_club": mc_club,
        "mc_jugadores": mc_jugadores,
        "mc_semanas": semana_labels,
        "total_checkins": len(checkins),
        "total_checkouts": len(checkouts),
        "insights": insights,
    }
