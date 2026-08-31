"""Conversational bot logic: build daily context from DB and query OpenAI."""
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Categoria, Checkin, Checkout, Club, Jugador, Staff

logger = logging.getLogger("services.bot_chat")

_SYSTEM = """\
Eres el asistente de *Mi Plantel*, una app de monitoreo deportivo para entrenadores de fútbol.
Tienes los datos del día de hoy para las categorías del entrenador.

Reglas estrictas:
- Responde siempre en español, de forma concisa y directa.
- Cuando te pidan un mensaje para WhatsApp, genera el texto listo para copiar, con emojis, claro y amigable.
- No inventes datos que no estén en el contexto.
- Si no hay datos para hoy, dilo con claridad.
- IMPORTANTE: Si el entrenador tiene más de una categoría en el contexto y su pregunta NO especifica a cuál se refiere, responde SOLO con: "¿De cuál categoría? (ej: Sub-16)" — nada más. Espera que indique la categoría antes de dar datos.
- Si el entrenador menciona una categoría específica (ej: "Sub-16", "sub 15", "primera"), responde SOLO con datos de esa categoría, ignora las demás.
- Si el entrenador solo tiene una categoría, responde directamente.
"""


async def responder_coach(db: AsyncSession, staff: Staff, texto: str) -> str:
    if not settings.openai_api_key:
        return "❌ El bot conversacional no está configurado (falta OPENAI_API_KEY en el servidor)."

    tz = ZoneInfo("America/Santiago")
    hoy = datetime.now(tz).date()
    contexto = await _build_context(db, staff, hoy)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM + "\n\n" + contexto},
            {"role": "user", "content": texto},
        ],
        max_tokens=700,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


async def _build_context(db: AsyncSession, staff: Staff, hoy: date) -> str:
    club = await db.get(Club, staff.club_id)
    base = settings.base_url.rstrip("/") if settings.base_url else ""

    if staff.categoria_ids:
        cat_rows = await db.execute(
            select(Categoria).where(
                Categoria.id.in_(staff.categoria_ids),
                Categoria.activo == True,
            )
        )
    else:
        cat_rows = await db.execute(
            select(Categoria).where(
                Categoria.club_id == staff.club_id,
                Categoria.activo == True,
            )
        )
    categorias = cat_rows.scalars().all()

    if not categorias:
        return f"Entrenador: {staff.nombre}\nFecha: {hoy.strftime('%d/%m/%Y')}\nNo tiene categorías activas asignadas."

    lines = [
        f"Entrenador: {staff.nombre}",
        f"Club: {club.nombre if club else staff.club_id}",
        f"Fecha: {hoy.strftime('%d/%m/%Y')} ({hoy.strftime('%A')})",
        "",
    ]

    for cat in categorias:
        jug_rows = await db.execute(
            select(Jugador).where(Jugador.categoria_id == cat.id, Jugador.activo == True)
        )
        jugadores = {j.id: j for j in jug_rows.scalars().all()}
        total = len(jugadores)
        if not total:
            lines += [f"=== {cat.nombre} ===", "Sin jugadores activos.", ""]
            continue

        ci_rows = await db.execute(
            select(Checkin).where(
                Checkin.jugador_id.in_(jugadores.keys()),
                Checkin.fecha == hoy,
                Checkin.asistencia == True,
            )
        )
        checkins = ci_rows.scalars().all()

        co_rows = await db.execute(
            select(Checkout).where(
                Checkout.jugador_id.in_(jugadores.keys()),
                Checkout.fecha == hoy,
            )
        )
        checkouts = co_rows.scalars().all()

        ids_ci = {ci.jugador_id for ci in checkins}
        ids_co = {co.jugador_id for co in checkouts}

        def _nombre(jid):
            j = jugadores[jid]
            return f"{j.nombre} {j.apellido}"

        sin_ci = [_nombre(jid) for jid in jugadores if jid not in ids_ci]
        sin_co = [_nombre(jid) for jid in ids_ci if jid not in ids_co]

        def _hooper(ci):
            if ci.sueno and ci.energia and ci.dolor_pre and ci.estres:
                return round((ci.sueno + ci.energia + (8 - ci.dolor_pre) + (8 - ci.estres)) / 4, 1)
            return None

        bvals = [h for ci in checkins if (h := _hooper(ci)) is not None]
        verde = sum(1 for v in bvals if v >= 5.0)
        amarillo = sum(1 for v in bvals if 3.5 <= v < 5.0)
        rojo = sum(1 for v in bvals if v < 3.5)

        rpe_vals = [co.rpe for co in checkouts if co.rpe is not None]
        rpe_prom = round(sum(rpe_vals) / len(rpe_vals), 1) if rpe_vals else None

        url = f"{base}/f/{club.slug}/{cat.nombre}" if base and club else "(URL no disponible)"

        lines += [
            f"=== CATEGORÍA: {cat.nombre} ===",
            f"Horario: {cat.hora_inicio}–{cat.hora_fin}",
            f"Total plantel: {total}",
            f"Check-ins hoy: {len(checkins)} / {total}",
            f"Sin check-in: {', '.join(sin_ci) if sin_ci else 'ninguno'}",
        ]
        if bvals:
            lines.append(f"Semáforo bienestar: 🟢{verde} 🟡{amarillo} 🔴{rojo}")
        lines += [
            f"Check-outs hoy: {len(checkouts)} / {len(checkins)}",
            f"Sin check-out: {', '.join(sin_co) if sin_co else 'ninguno'}",
        ]
        if rpe_prom is not None:
            lines.append(f"RPE promedio: {rpe_prom}")
        lines += [f"URL formulario: {url}", ""]

    return "\n".join(lines)
