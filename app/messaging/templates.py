"""WhatsApp template definitions.

These bodies must be registered and approved in Meta Business Manager
under the same names, in Spanish (es_CL or es). The code only references
templates by name + positional variables; the bodies here are used to:
  - render the human-readable copy stored in alertas_log
  - print console previews with the FakeProvider
"""

TEMPLATES: dict[str, str] = {
    # Formato unificado: título corto + link al informe.
    # El detalle completo vive en la página web — WhatsApp es solo el ping.
    "semaforo_checkin": (
        "🟡 *Semáforo · {{1}}*\n"
        "📊 {{2}}"
    ),
    "alerta_bienestar_rojo": (
        "🔴 *Bienestar bajo · {{1}}*\n"
        "📊 {{2}}"
    ),
    "alerta_bienestar_rojo_tardio": (
        "⚠️ *Check-in tardío en rojo · {{1}}*\n"
        "📊 {{2}}"
    ),
    "alerta_bienestar": (
        "🔻 *Tendencia baja · {{1}}*\n"
        "📊 {{2}}"
    ),
    "alerta_molestia": (
        "🩹 *Molestia reportada · {{1}}*\n"
        "📊 {{2}}"
    ),
    "alerta_tendencia_molestia": (
        "🔁 *Molestia recurrente · {{1}}*\n"
        "📊 {{2}}"
    ),
    "alerta_inasistencia": (
        "❌ *Inasistencia · {{1}}*\n"
        "📊 {{2}}"
    ),
    "alerta_carga": (
        "📈 *Carga alta · {{1}}*\n"
        "📊 {{2}}"
    ),
    "recordatorio_checkin": (
        "🔔 *Recordatorio · {{1}}*\n"
        "📊 {{2}}"
    ),
    # Nuevos triggers basados en comportamiento
    "primer_aviso_checkin": (
        "✅ *3 check-ins · {{1}}*\n"
        "📊 {{2}}"
    ),
    "resumen_post": (
        "📋 *Post-entreno · {{1}}*\n"
        "📊 {{2}}"
    ),
    "dashboard_dia": (
        "📊 *Resumen del día · {{1}}*\n"
        "📊 {{2}}"
    ),
    # Legacy — no se usan en el flujo activo
    "semaforo_diario": "🚦 *Semáforo {{1}}* — {{2}}",
    "resumen_diario":  "📊 *Resumen {{1}}* — {{2}}",
}


def render(template: str, variables: list[str]) -> str:
    """Replace {{1}}, {{2}}, ... with the given values. Used for logs and fake sends."""
    body = TEMPLATES[template]
    for i, value in enumerate(variables, start=1):
        body = body.replace("{{" + str(i) + "}}", str(value))
    return body
