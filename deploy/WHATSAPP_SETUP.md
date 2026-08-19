# Configuración WhatsApp Cloud API — Mi Plantel

Guía paso a paso documentada durante la configuración real (18 jul 2026).
**Portafolio empresarial:** Said Coach (verificación completada)
**App en Meta:** MiPlantel — ID `1565651274920480`, tipo **Empresa**
**Número de producción:** +56 9 5764 6975 (chip nuevo, nunca registrado en WhatsApp)
**Phone ID:** `1214369248428146` · **WABA ID:** `1709528966935894`

---

## Paso 1: Crear la app en Meta for Developers

> ⚠️ **NO usar** el caso de uso "Conecta con los clientes a través de WhatsApp": deja la app
> con tipo "Ninguno" y WhatsApp nunca aparece como producto. Si además reintentas varias
> veces, Meta muestra "Esta acción no está permitida" (rate-limit temporal).

Flujo correcto:

1. `developers.facebook.com` → **Mis apps** → **Crear app**
2. Elegir **"Otro"** → Siguiente
3. Elegir **"Negocio"** → Siguiente
4. Nombre `MiPlantel`, email de contacto, portafolio **Said Coach** → **Crear aplicación**

Resultado: app tipo **Empresa** y WhatsApp aparece solo en el menú izquierdo ("Inicio rápido").

## Paso 2: Número de teléfono

En **WhatsApp → Configuración de la API**:

- Meta regala un número de prueba (gratis 90 días, solo para testear).
- **Paso 5 "Añadir número de teléfono"**: registrar el chip nuevo.
  - Nombre para mostrar: `Mi Plantel` · Categoría: Deportes/Educación
  - Verificación por SMS al chip (tenerlo puesto en un teléfono).
- Anotar de esta pantalla: **Identificador del número de teléfono** (phone ID) y
  **Identificador de la cuenta de WhatsApp Business** (WABA ID).

## Paso 3: Método de pago

Banner "Te falta un método de pago" → **Añadir método de pago** (tarjeta). Sin esto no se
pueden iniciar conversaciones. Meta cobra por conversación iniciada por la empresa.

## Paso 4: Webhook

En **WhatsApp → Configuración**:

- URL de devolución de llamada: `https://miplantel.app/webhooks/whatsapp`
- Identificador de verificación: el valor de `WHATSAPP_VERIFY_TOKEN` del `.env` del VPS
  (actual: `miplantel2026`)

> ⚠️ Si falla la validación: (1) el token del `.env` no coincide, o (2) el contenedor no
> recargó el `.env`. `docker compose restart` **NO** relee variables de entorno — usar
> `docker compose -f docker-compose.prod.yml up -d miplantel`.
> Probar a mano: `curl "https://miplantel.app/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=<TOKEN>&hub.challenge=test123"` → debe responder `test123`.

## Paso 5: Token permanente (usuario del sistema)

El token del botón "Generar identificador de acceso" **expira en 24 h**. Para producción:

1. `business.facebook.com` → **Configuración del negocio** → **Usuarios → Usuarios del sistema**
2. **Añadir** → nombre `miplantel-bot`, rol **Empleado**
3. **Asignar activos** → **Aplicaciones** → MiPlantel → **Administrar la aplicación** (acceso total)
4. **Asignar activos** → **Cuentas de WhatsApp** → cuenta de MiPlantel (WABA) → **control total**
   > ⚠️ Este paso es fácil de olvidar: la app y la cuenta de WhatsApp son activos SEPARADOS.
   > Sin este, todo parece bien configurado pero Meta responde 400 al enviar:
   > `"Object with ID '<phone_id>' does not exist, cannot be loaded due to missing permissions..."`
   > (código 100, subcódigo 33). Al asignar el activo el token existente empieza a funcionar —
   > no hay que regenerarlo.
5. **Generar identificador** → app MiPlantel → permisos:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
6. **Copiar el token de inmediato** (Meta lo muestra una sola vez). No expira.

## Paso 6: Configurar el VPS

En `/opt/miplantel/.env` (editar por SSH, nunca pegar tokens en chats/documentos):

```
ENVIRONMENT=production        # ⚠️ con "development" la app usa FakeProvider aunque haya token
DEBUG=false
WHATSAPP_TOKEN=<token permanente del usuario del sistema>
WHATSAPP_PHONE_ID=1214369248428146
WHATSAPP_VERIFY_TOKEN=miplantel2026
```

Aplicar cambios (siempre `up -d`, no `restart`):

```bash
cd /opt/miplantel && docker compose -f docker-compose.prod.yml up -d miplantel
```

Verificar que quedó en modo real:

```bash
docker exec miplantel-miplantel-1 python -c \
  "from app.config import settings; print('modo fake:', settings.use_fake_messaging)"
# → modo fake: False
```

## Paso 7: Plantillas de mensajes

`business.facebook.com/wa/manage/message-templates/` → **Crear plantilla**.
Para todas: categoría **Servicio**, tipo **Predeterminado**, idioma **Spanish (CHL)**,
tipo de variable **Número**, sin título, sin pie, sin botones.

> Reglas que Meta impone al cuerpo:
> - Las variables no pueden estar al principio ni al final → terminar con una frase fija.
> - Muchas variables exigen un texto proporcionalmente largo.
> - Pide un valor de ejemplo por variable (sin datos reales de clientes).
> - Los templates NO se pueden renombrar después de creados.

Las 8 plantillas registradas (18 jul 2026) — los nombres deben calzar 1:1 con
`app/messaging/templates.py`:

| # | Nombre | Variables (ejemplos) |
|---|--------|----------------------|
| 1 | `resumen_diario` | Sub-14 · 18/07/2026 · 20/24 · García, López · Pérez (rodilla, leve) · Martínez · 7.2 · 540 |
| 2 | `alerta_molestia` | Sub-14 · Pedro Reyes · Rodilla · check-in |
| 3 | `alerta_tendencia_molestia` | Sub-14 · Pedro Reyes · 3 · Rodilla |
| 4 | `alerta_bienestar` | Sub-14 · Pedro Reyes · sueño (promedio 1.7) · 3 |
| 5 | `alerta_carga` | Sub-14 · Pedro Reyes · 850 · 700 |
| 6 | `recordatorio_checkin` | Sub-14 · mensaje libre del recordatorio · 12 |
| 7 | `alerta_inasistencia` | Sub-14 · Pedro Reyes · Enfermedad |
| 8 | `semaforo_diario` | Sub-14 · 18/07/2026 · VERDE · 20/24 · 5.8 · 5.5 · 6.1 · 2.3 |

> Nota histórica: el código usaba `recordatorio_staff`; el template en Meta quedó como
> `recordatorio_checkin` y como no se puede renombrar, se ajustó el código (commit 18 jul).

Estados: "En revisión" → "Activa: calidad pendiente" (= aprobada, sin datos de calidad aún).
La aprobación suele tardar minutos.

## Paso 8: Prueba de punta a punta

1. Agregar un staff real al club en producción (por panel de admin, o por SQL):
   ```sql
   INSERT INTO mp_staff (club_id, nombre, telefono_whatsapp, rol, recibe_alertas, recibe_resumen, activo)
   VALUES (1, 'Marcelo Said', '56995995678', 'ADMIN', true, true, true);
   -- teléfono SIN "+": formato 569XXXXXXXX
   ```
2. Disparar una alerta real — un check-in con molestia bloqueante por la API:
   ```bash
   curl -X POST https://miplantel.app/api/checkin -H "Content-Type: application/json" \
     -d '{"jugador_id": 2, "fecha": "2026-07-18", "asistencia": true, "sueno": 5,
          "energia": 5, "animo": 5, "dolor_pre": 3, "molestia_previa": true,
          "molestia_zona": "Rodilla", "molestia_severidad": "bloqueante"}'
   ```
3. Revisar el resultado del envío en la tabla de log:
   ```sql
   SELECT id, tipo, destinatario, estado_envio, respuesta_api
   FROM mp_alertas_log ORDER BY id DESC LIMIT 3;
   ```
   - `estado_envio = sent/delivered/read` → todo OK (los estados los actualiza el webhook)
   - `failed` + error 100/33 "does not exist... missing permissions" → falta asignar la
     **Cuenta de WhatsApp** al usuario del sistema (ver Paso 5.4)
   - `failed` + error de destinatario → en modo desarrollo, agregar el número como
     destinatario de prueba en Configuración de la API
   - `failed` + error 132001 "Template name does not exist in the translation" → el código
     de idioma del envío no calza con el idioma del template en Meta. Los templates están
     en `Spanish (CHL)` = **`es_CL`**; el provider debe usar exactamente ese código
     (`WhatsAppCloudProvider(lang="es_CL")` en `app/messaging/whatsapp_cloud.py`).

**Primer envío real exitoso: 18 jul 2026, alerta_molestia → 56995995678, `estado_envio=sent`.**

## Paso 9: Pasar la app a modo Producción

Requisitos previos (todo en **Configuración de la aplicación → Básica**):

1. **URL de política de privacidad**: `https://miplantel.app/privacidad`
2. **URL de condiciones del servicio**: `https://miplantel.app/terminos`
3. **Eliminación de datos del usuario**: "URL de instrucciones" → `https://miplantel.app/privacidad`
   (la sección 7 explica la eliminación por email — suficiente para Meta)
4. **Categoría** de la app si está vacía
5. Guardar cambios → toggle superior **"En desarrollo" → "En producción"**

> La App Secret NO se usa en nuestra integración (solo el token del usuario del sistema).

**COMPLETADO 18 jul 2026:**
- ✅ 8/8 plantillas aprobadas por Meta
- ✅ Staff de prueba cargado y primer mensaje real recibido
- ✅ Páginas legales publicadas (`/privacidad`, `/terminos`)
- ✅ App en modo PRODUCCIÓN — cualquier número de staff registrado recibe alertas

## Regla de oro del proyecto

**El sistema JAMÁS envía WhatsApp a jugadores (menores de edad). Solo a staff.**
