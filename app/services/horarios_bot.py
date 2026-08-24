"""Parse coach WhatsApp messages to extract training schedules.

The coach sends a free-text message like:
  "esta semana Sub-13 entrena martes y jueves a las 15:30"
  "el Sub-14 va a entrenar lunes miércoles viernes a las 17:00"

We use GPT-4o-mini to extract: category name + time + days, then update mp_categorias.
"""
import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger("services.horarios_bot")

DIAS_MAP = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}

_SYSTEM = (
    "Eres un asistente que extrae información de horarios de entrenamiento "
    "de mensajes de entrenadores de fútbol. Respondes SOLO con JSON válido, sin texto extra."
)

_PROMPT = """El entrenador envió este mensaje:
"{message}"

Las categorías disponibles en su club son: {categorias}

Extrae los cambios de horario. Para cada categoría mencionada, devuelve:
- "categoria": nombre exacto de la lista de categorías disponibles
- "hora_inicio": hora en formato "HH:MM" (24h), o null si no se menciona.
  Importante: convierte AM/PM correctamente (ej: "8:30 am" → "08:30", "8:30 pm" → "20:30",
  "6 pm" → "18:00"). Si no se indica AM/PM y la hora es ≤ 12, asume AM (mañana).
- "dias": lista de enteros [0=lunes,1=martes,2=miércoles,3=jueves,4=viernes,5=sábado,6=domingo], o null si no se mencionan.
  "lunes a viernes" equivale a [0,1,2,3,4].

Responde con un array JSON. Ejemplo:
[{{"categoria": "Sub-13", "hora_inicio": "15:30", "dias": [1, 3]}}]

Si el mensaje no contiene información de horarios, responde con: []
"""


async def parsear_horario(mensaje: str, categorias: list[str]) -> list[dict]:
    """Call GPT-4o-mini to extract schedule changes from a coach message.

    Returns list of dicts: [{categoria, hora_inicio, dias}]
    Empty list if no schedule info found or on error.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY no configurada — usando parser regex fallback")
        return _parsear_regex(mensaje, categorias)

    prompt = _PROMPT.format(
        message=mensaje,
        categorias=", ".join(categorias),
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "max_tokens": 256,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
        if resp.status_code != 200:
            logger.error("OpenAI API error %s: %s", resp.status_code, resp.text)
            return []
        content = resp.json()["choices"][0]["message"]["content"].strip()
        parsed = json.loads(content)
        # GPT with json_object mode wraps in an object — unwrap if needed
        if isinstance(parsed, dict):
            parsed = parsed.get("cambios") or parsed.get("horarios") or list(parsed.values())[0] if parsed else []
        return parsed if isinstance(parsed, list) else []
    except Exception:
        logger.exception("Error parseando horario con OpenAI")
        return []


def _parsear_regex(mensaje: str, categorias: list[str]) -> list[dict]:
    """Fallback regex parser for when Claude API is unavailable."""
    import re
    resultados = []
    msg_lower = mensaje.lower()

    for cat in categorias:
        if cat.lower() not in msg_lower:
            continue

        hora = None
        match = re.search(r"(\d{1,2})[:\.](\d{2})", mensaje)
        if match:
            h, m = int(match.group(1)), int(match.group(2))
            if 0 <= h <= 23 and 0 <= m <= 59:
                hora = f"{h:02d}:{m:02d}"

        dias = [v for k, v in DIAS_MAP.items() if k in msg_lower]
        dias = sorted(set(dias)) or None

        if hora or dias:
            resultados.append({"categoria": cat, "hora_inicio": hora, "dias": dias})

    return resultados


async def enviar_texto_whatsapp(to: str, texto: str) -> None:
    """Send a free-form text reply to a WhatsApp number (within 24h window)."""
    if settings.use_fake_messaging:
        logger.info("[FAKE WA] → %s: %s", to, texto)
        return
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": texto},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.whatsapp_api_url, json=payload, headers=headers)
    except Exception:
        logger.exception("Error enviando texto WhatsApp a %s", to)
