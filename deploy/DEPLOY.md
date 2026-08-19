# Deploy de Mi Plantel en el VPS

VPS: 166.1.90.152 (Ubuntu, ya corre Supabase + n8n + Evolution API en Docker).
Dominio: miplantel.app (Namecheap, A records → VPS). Los `.app` exigen HTTPS.

## 1. Subir el código

Desde el Mac:

```bash
rsync -av --exclude .venv --exclude __pycache__ --exclude .env \
  ~/dev/assist-tracker/ root@166.1.90.152:/opt/miplantel/
```

## 2. Configurar variables

En el VPS:

```bash
cd /opt/miplantel
cp .env.production.example .env
openssl rand -hex 32   # → pegar como SECRET_KEY
nano .env              # completar SECRET_KEY, ADMIN_PASSWORD, DB_PASSWORD, WHATSAPP_VERIFY_TOKEN
```

## 3. Levantar app + base de datos

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f miplantel   # ver que migre y arranque
curl http://127.0.0.1:8001/health                             # {"status":"ok"}
```

## 4. Reverse proxy con SSL (Caddy)

Antes, revisar qué ocupa los puertos 80/443 hoy:

```bash
ss -tlnp | grep -E ':80 |:443 '
```

- **Si están libres** → instalar Caddy en el host:
  ```bash
  apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  apt update && apt install caddy
  cp deploy/Caddyfile /etc/caddy/Caddyfile
  systemctl reload caddy
  ```
- **Si ya hay un nginx/traefik/caddy** → agregar ahí el virtual host `miplantel.app → 127.0.0.1:8001` en vez de instalar otro.

## 5. Seed de Coquimbo (opcional, solo primera vez)

```bash
docker compose -f docker-compose.prod.yml exec miplantel python scripts/seed.py
```

## 6. Verificar

- https://miplantel.app → landing
- https://miplantel.app/registro → crear club de prueba
- https://miplantel.app/f/coquimbo-unido/Sub-13 → formulario
- https://miplantel.app/admin/super → superadmin

## Pendientes post-deploy

- Plantillas WhatsApp en Meta Business Manager (textos en `app/messaging/templates.py`)
- Webhook Meta: `https://miplantel.app/webhooks/whatsapp` + WHATSAPP_VERIFY_TOKEN
- Completar WHATSAPP_TOKEN y WHATSAPP_PHONE_ID en `.env` (hasta entonces, mensajería simulada)
- Teléfonos reales de Raúl, Marcelo y Claudio en el staff
- Backups: `docker compose -f docker-compose.prod.yml exec miplantel-db pg_dump -U miplantel miplantel > backup.sql` (cron diario recomendado)
