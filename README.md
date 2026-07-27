# Biblioteca Personal

App web para catalogar, subir, buscar y descargar los libros de la biblioteca personal, con aprobación de subidas de amigos autorizados. Reemplaza el flujo anterior (scripts `main.py`/`incremental.py` + Google Sheet).

## Desarrollo local

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # completar valores, ver abajo
./venv/bin/uvicorn app.main:app --reload --port 8010
```

Abrir `http://localhost:8010`.

### Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `OWNER_EMAIL` | Tu email — se siembra como `owner` en el primer arranque. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Credenciales OAuth (Google Cloud Console → APIs & Services → Credentials). Requiere configurar antes el **OAuth consent screen** (External, con tu email y los de tus amigos en "Test users"), si no la consola rebota al crear el client ID sin mostrar error. |
| `SESSION_SECRET_KEY` | Generar con `python3 -c "import secrets; print(secrets.token_hex(32))"`. Distinta en dev y producción. |
| `BASE_URL` | `http://localhost:8010` en dev, `https://biblioteca.tudominio.com` en producción. Debe coincidir exactamente con un "Authorized redirect URI" (`{BASE_URL}/auth/callback`) en la consola de Google. |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta al `service_account.json` (nunca se commitea). |
| `DATABASE_URL` / `PENDING_DIR` | SQLite local + staging de subidas pendientes. En Docker se sobreescriben para apuntar al volumen `/data`. |

## Arquitectura

Ver `CLAUDE.md` para el detalle de módulos. Resumen: FastAPI + Jinja2, SQLite (usuarios/allowlist + cola de aprobación) y BigQuery (catálogo publicado, única fuente de verdad de los libros ya aprobados). Los archivos viven solo en Google Cloud Storage — nunca se exponen URLs de GCS al cliente, todas las descargas pasan por la app (`/descargar/{id}`) en streaming.

## Despliegue en el homelab (Docker + Cloudflare Tunnel)

### 1. Prerrequisitos
- Dominio propio en la DNS de Cloudflare (comprado directo en Cloudflare Registrar, o traído de otro registrador cambiando nameservers).
- Docker y Docker Compose en el homelab.
- `service_account.json` y `.env` completados (con `BASE_URL` apuntando al dominio real) copiados al servidor, **nunca** al repo.

### 2. Crear el túnel de Cloudflare
1. [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com/) → **Networks → Tunnels → Create a tunnel**.
2. Tipo: **Cloudflared**. Nómbralo (ej. `biblioteca-personal`).
3. En "Choose your environment", selecciona **Docker** — te da un comando con un `TUNNEL_TOKEN`. Copia solo el token (después del `--token`) a `CLOUDFLARE_TUNNEL_TOKEN` en tu `.env` de producción.
4. En "Public Hostname", agrega: subdominio (ej. `biblioteca`) + tu dominio + servicio `HTTP://app:8000` (el nombre `app` es el del servicio en `docker-compose.yml`, se resuelven por DNS interno de Docker).
5. En Google Cloud Console, agrega `https://biblioteca.tudominio.com/auth/callback` como Authorized redirect URI adicional (no reemplaces la de `localhost`, sirve para seguir probando en dev).

### 3. Levantar los contenedores

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

El servicio `app` no publica ningún puerto al host — solo `cloudflared` lo alcanza por la red interna de Docker. El volumen `biblioteca_data` guarda el SQLite (`users`, `pending_uploads`, `categorias`) y el staging temporal de subidas.

### 4. Verificar
- `https://biblioteca.tudominio.com` carga el login desde una red distinta a la del homelab (ej. datos móviles) — confirma que no depende de Tailscale/VPN ni de puertos abiertos en el router.
- Login con Google funciona y el catálogo muestra los libros reales.
- Agregar un amigo desde `/panel`, pedirle que suba un libro, aprobarlo, confirmar que aparece en el catálogo.

## Scripts heredados

`main.py`, `incremental.py`, `listar_formatos.py` y `organizar_libros.ipynb` quedan archivados como referencia histórica — el flujo web (`app/`) los reemplaza por completo.
