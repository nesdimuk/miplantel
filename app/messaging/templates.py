"""WhatsApp template definitions.

These bodies must be registered and approved in Meta Business Manager
under the same names, in Spanish (es_CL or es). The code only references
templates by name + positional variables; the bodies here are used to:
  - render the human-readable copy stored in alertas_log
  - print console previews with the FakeProvider
"""

TEMPLATES: dict[str, str] = {
    "alerta_molestia": (
        "🔴 *Molestia — no puede entrenar* — {{1}}\n"
        "{{2}} reportó molestia en *{{3}}* ({{4}}) y NO puede entrenar.\n"
        "Revisa el detalle en el panel."
    ),
    "alerta_tendencia_molestia": (
        "🔁 *Molestia recurrente* — {{1}}\n"
        "{{2}} lleva *{{3}} reportes* de molestia en los últimos 14 días (zona: {{4}}).\n"
        "Considera evaluarlo antes del próximo entrenamiento."
    ),
    "alerta_inasistencia": (
        "❌ *Inasistencia* — {{1}}\n"
        "{{2}} avisó que hoy no asistirá.\n"
        "Motivo: {{3}}"
    ),
    "semaforo_diario": (
        "🚦 *Semáforo {{1}}* — {{2}}\n"
        "Estado del plantel: *{{3}}*\n"
        "Check-ins: {{4}} | Sueño: {{5}} | Energía: {{6}} | Ánimo: {{7}} | Dolor: {{8}}"
    ),
    "semaforo_checkin": (
        "⚠️ *Pre-entrenamiento — {{1}}*\n\n"
        "{{2}}\n\n"
        "✅ {{3}} de {{4}} jugadores registraron check-in"
    ),
    "resumen_diario": (
        "📊 *Resumen {{1}}* — {{2}}\n"
        "Asistencia: {{3}}\n"
        "Inasistencias: {{4}}\n"
        "Molestias: {{5}}\n"
        "Sin check-out: {{6}}\n"
        "RPE promedio: {{7}} | Carga promedio: {{8}}"
    ),
    "alerta_bienestar": (
        "🔻 *Bienestar bajo* — {{1}}\n"
        "{{2}} registra {{3}} muy bajo en sus últimos {{4}} registros.\n"
        "Sugerimos conversar con el jugador."
    ),
    "alerta_bienestar_rojo": (
        "🔴 *Bienestar bajo hoy* — {{1}}\n"
        "{{2}} viene en rojo:\n"
        "Sueño {{3}} · Energía {{4}} · Ánimo {{5}} · Dolor {{6}}"
    ),
    "alerta_bienestar_rojo_tardio": (
        "⚠️ *Check-in tardío en rojo* — {{1}}\n"
        "{{2}} registró después del reporte y viene en rojo:\n"
        "Sueño {{3}} · Energía {{4}} · Ánimo {{5}} · Dolor {{6}}"
    ),
    "recordatorio_checkin": (
        "🔔 *Recordatorio* — {{1}}\n"
        "{{2}}\n"
        "Check-ins hasta ahora: {{3}}"
    ),
    "alerta_carga": (
        "📈 *Carga alta* — {{1}}\n"
        "{{2}} acumula una carga semanal de *{{3}}* (umbral: {{4}}).\n"
        "Considera ajustar su volumen de entrenamiento."
    ),
}


def render(template: str, variables: list[str]) -> str:
    """Replace {{1}}, {{2}}, ... with the given values. Used for logs and fake sends."""
    body = TEMPLATES[template]
    for i, value in enumerate(variables, start=1):
        body = body.replace("{{" + str(i) + "}}", str(value))
    return body
