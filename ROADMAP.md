# 🗺️ Roadmap Mi Plantel — de hoy a la primera venta

Actualizado: 2026-07-06 (día del deploy a producción)

---

## Semana 1 (7–13 julio) — Pruebas de fuego

Objetivo: usar el producto TÚ MISMO como si fueras un club nuevo, todos los días, y anotar cada fricción.

### Lunes–Martes: prueba end-to-end como cliente
- [ ] Registrar un club de prueba real en https://miplantel.app/registro desde el celular
- [ ] Completar el onboarding entero: categoría → pegar lista de 20 jugadores → 2 staff → imprimir QR en papel
- [ ] Pegar el QR en una pared y hacer check-in/check-out escaneándolo de verdad (no desde el navegador)
- [ ] Cronometrar: ¿el check-in toma de verdad <30 segundos? ¿un niño de 13 años lo entiende solo?

### Miércoles–Jueves: probar los automatismos en producción
- [ ] Configurar recordatorio y horarios de una categoría para HOY y verificar que el tick dispare: recordatorio → semáforo → resumen (revisar log de alertas en el panel)
- [ ] Simular molestia e inasistencia y revisar que las alertas queden registradas
- [ ] Probar dashboard con 3-4 días de datos acumulados
- [ ] Probar en 3 celulares distintos (iPhone viejo, Android barato, tablet) — ahí aparecen los bugs de verdad

### Viernes: WhatsApp real
- [ ] Crear app en Meta for Developers + WhatsApp Business (usar el número que definas para el producto, NO tu personal)
- [ ] Registrar las 7 plantillas (textos listos en `app/messaging/templates.py`) — aprobación demora 1–48 h
- [ ] Configurar webhook `https://miplantel.app/webhooks/whatsapp` con el VERIFY_TOKEN del `.env`
- [ ] Pegar WHATSAPP_TOKEN y PHONE_ID en el `.env` del VPS y reiniciar → primer WhatsApp real a tu número

### Fin de semana: Coquimbo real
- [ ] Registrar el Coquimbo Unido real (o migrar) con jugadores y staff verdaderos
- [ ] Presentárselo a Raúl y Claudio para que lo usen la semana 2

## Semana 2 (14–20 julio) — Piloto real + pulir

- [ ] Coquimbo usando el sistema en entrenamientos reales (lunes/miércoles/viernes)
- [ ] Reunión de 15 min con el staff después de cada entrenamiento: ¿qué alertas sirvieron? ¿qué sobra?
- [ ] Backup automático diario de la DB (cron con pg_dump — comando en deploy/DEPLOY.md)
- [ ] Corregir todo lo que apareció en semana 1
- [ ] Features probables post-feedback: editar/eliminar registros desde admin, exportar a Excel/CSV (los PF lo van a pedir sí o sí)

## Semana 3–4 — Preparar la venta

**Producto:**
- [ ] Página de precios en la landing (sugerencia inicial: plan por categoría/mes, piloto gratis 30 días)
- [ ] Términos de servicio + política de privacidad (CRÍTICO: datos de menores — consentimiento del club/apoderados; asesorarse)
- [ ] Email transaccional de bienvenida al registrarse (hoy no hay ninguno)
- [ ] Recuperación de contraseña (hoy no existe — necesario antes de clientes reales)

**Comercial:**
- [ ] Video demo de 90 segundos (pantalla + celular) para WhatsApp/Instagram
- [ ] PDF one-pager: problema → solución → precio → QR a la landing
- [ ] Caso de éxito Coquimbo: 2-3 números concretos ("detectamos X molestias antes de que fueran lesión", "% adhesión")
- [ ] Lista de 20 clubes objetivo (Coquimbo/La Serena primero, luego región) y agendar 5 demos

## Mes 2 — Primeros clientes pagando

- [ ] Cobros: link de pago simple (Mercado Pago / Flow) manual al principio; automatizar después
- [ ] Límites por plan (nº categorías/jugadores) si haces freemium
- [ ] Métricas de uso por club en el superadmin (¿quién está activo? ¿quién se enfría?) para retención
- [ ] Monitoreo: alerta si el sitio se cae (UptimeRobot gratis) + revisión semanal de logs

## Deuda técnica conocida (no urgente, no olvidar)

- Passwords con sha256 simple → migrar a bcrypt/argon2 cuando haya clientes pagando
- Rate limiting en /registro y /api/checkin (hoy sin protección anti-spam)
- El scheduler corre dentro del mismo proceso web (si escalas a 2+ réplicas, separarlo)
- `alertas_log.mensaje` crece sin límite → job de limpieza a los 6 meses
- Tests E2E del formulario (hoy solo se prueba la API, no el JS)
- Horarios por día de la semana (hoy la categoría tiene UN horario para todos sus días de
  entrenamiento; afecta recordatorios "minutos antes", duración para carga y semáforo por
  horario). Detectado en ensayo 19-jul — validar con clubes del piloto antes de construir.

---

**Regla de oro de estas semanas:** no agregar features nuevas hasta que Coquimbo haya usado el sistema 2 semanas seguidas. El feedback real vale más que cualquier idea nuestra.
