# ⚽ Mi Plantel — miplantel.app

SaaS de monitoreo de bienestar y carga de entrenamiento para clubes de fútbol (formativo y profesional) de Chile y LATAM. Los jugadores responden un formulario de 30 segundos escaneando un QR; el cuerpo técnico recibe alertas y resúmenes por WhatsApp y ve la evolución del plantel en dashboards.

**Producción:** https://miplantel.app · VPS 166.1.90.152 · Piloto: Coquimbo Unido (Sub-13/Sub-14).

---

## El problema que resuelve

En el fútbol formativo nadie sabe cómo llegan los jugadores a entrenar: si durmieron mal, si arrastran una molestia, si están sobrecargados. Las lesiones y el abandono se detectan tarde. Las soluciones profesionales (Kitman Labs, Catapult) son carísimas y requieren apps que los juveniles no instalan.

**Mi Plantel:** cero fricción. Sin app, sin login, sin número de teléfono del jugador (son menores — el sistema JAMÁS les escribe). Un QR pegado en el camarín.

## Cómo funciona (flujo diario)

1. **Check-in (antes de entrenar):** el jugador escanea el QR → elige su nombre → ¿vas a entrenar? → 4 escalas Hooper 1-7 (sueño, energía, ánimo, dolor) → ¿molestia física? (zona o texto libre). Si no va: motivo de inasistencia.
2. **Alertas inmediatas al staff** por WhatsApp: molestia física, inasistencia.
3. **Semáforo diario** 🟢🟡🟠🔴: al juntarse N check-ins (configurable), promedio del plantel → WhatsApp al staff antes del entrenamiento.
4. **Check-out (después):** RPE Borg 0-10 → carga = RPE × duración fija de la categoría → escalas físico/rendimiento → ¿molestia nueva?
5. **Resumen diario** a la hora configurada: asistencia, molestias, RPE y carga promedio.
6. **Alertas de tendencia:** sueño/ánimo ≤2 sostenido (3 registros), carga semanal sobre umbral. ACWR (carga aguda/crónica) con guardia anti-falso-positivo (mín. 4 sesiones y 7 días de historia).
7. **Dashboard** por club (password propio): Hooper 7d, adhesión/proceso por jugador, distribución RPE, señales de riesgo, insights automáticos.

## Modelo de negocio (multi-tenant white-label)

- Registro self-service en `/registro`: cualquier club se crea su cuenta (nombre, email, contraseña, país) y recibe su URL propia (`/admin/{slug}`), su QR y su dashboard.
- Aislamiento total entre clubes (un club jamás ve datos de otro; devuelve 404).
- Superadmin (`/admin/super`, nosotros) ve todos los clubes.
- Onboarding guiado: categoría → plantel (alta masiva pegando lista) → staff → QR.

## Stack técnico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 async, asyncpg |
| DB | PostgreSQL 16 (tablas con prefijo `mp_`), migraciones Alembic |
| Scheduler | APScheduler, tick 1 min, timezone por club, envíos tardíos self-healing |
| Frontend | Jinja2 server-rendered + JS vanilla (formulario móvil multi-pantalla) |
| Mensajería | `MessagingProvider` ABC → `WhatsAppCloudProvider` (Meta) / `FakeProvider` (dev) |
| Auth | Cookies firmadas HMAC (sin tabla de sesiones). Scopes: `admin` (super) y `club:{slug}` |
| QR | segno |
| Tests | pytest-asyncio (69 tests, loop_scope=session) |
| Deploy | Docker Compose en VPS + nginx (host) + certbot SSL |

## Estructura del código

```
app/
├── main.py              # FastAPI, routers, lifespan (scheduler)
├── config.py            # pydantic-settings (.env)
├── db/models.py         # 9 tablas mp_*: Club, Categoria, Jugador, Staff,
│                        #   Checkin, Checkout, SesionDia, Recordatorio, AlertaLog
├── api/
│   ├── auth.py          # HMAC cookies, scopes, require_admin multi-tenant
│   ├── routers/
│   │   ├── checkin.py / checkout.py   # POST /api/* (contadores atómicos ON CONFLICT)
│   │   ├── forms.py     # GET /f/{club}/{cat} formulario + /qr/...
│   │   ├── registro.py  # landing / + /registro self-service
│   │   ├── admin.py     # panel: login club/super, CRUD, vista día, reenvíos, log
│   │   ├── dashboards.py# /d/{club} con password por club
│   │   └── webhooks.py  # estados de entrega Meta (sent/delivered/read)
├── services/            # semaforo, resumen, alertas, bienestar, carga (ACWR),
│                        #   gamificacion (racha/posición), recordatorios, dashboard
├── scheduler/jobs.py    # tick: recordatorios → semáforo → resumen
├── messaging/           # ABC + Meta + Fake + plantillas (7)
└── templates/ static/   # form móvil, admin, dashboard, landing
```

## Convenciones importantes

- `dias_entrenamiento`: 0=lunes … 6=domingo
- Carga = RPE × duración de la sesión de la categoría (el jugador NO elige duración)
- Semáforo: score = (sueño + energía + ánimo + (8 − dolor)) / 4
- Claims atómicos (semáforo/resumen/recordatorio 1 vez al día) vía UPDATE…RETURNING
- Passwords de clubes: sha256 hex. Cookie 12 h.
- Los `.app` fuerzan HTTPS — nunca probar producción por http

## Desarrollo local

```bash
brew services start postgresql@16
cd ~/dev/assist-tracker && source .venv/bin/activate   # Python 3.12 (¡no 3.14!)
alembic upgrade head && python scripts/seed.py
uvicorn app.main:app --host 0.0.0.0 --port 8000        # 0.0.0.0 para probar desde el celular
python -m pytest tests/ -q                              # 69 tests
```

Deploy a producción: ver `deploy/DEPLOY.md` (rsync + docker compose + nginx).

## Credenciales del piloto

- Club Coquimbo Unido (dev): `staff@coquimbounido.cl` / `coquimbo-admin-2026` · dashboard: `coquimbo2026`
- Superadmin prod: en `.env` del VPS (`/opt/miplantel/.env`)
