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

## Seguridad de subidas y sesiones

- Máximo **700 MB decimales (700.000.000 bytes)** por archivo. `MAX_UPLOAD_BYTES` permite reducirlo, nunca aumentarlo por encima de 700 MB. El cuerpo multipart admite 64 KiB adicionales para metadatos; el archivo tiene su propio límite exacto.
- Formatos permitidos: **PDF, EPUB, MOBI, AZW, AZW3, FB2, CBR, CBZ, TXT y RTF**. Se valida extensión y firma/estructura. EPUB requiere su mimetype y contenedor; CBZ admite imágenes y `ComicInfo.xml`. Se rechazan ZIP64, archivos ZIP cifrados y directorios ZIP excesivos. TXT admite UTF-8 o UTF-16 con BOM; FB2, UTF-8 sin DTD/entidades. AZW/AZW3 deben usar el contenedor MOBI. Estos controles no sustituyen un antivirus ni garantizan que un documento sea inocuo al abrirlo.
- Una recepción de archivo a la vez, protegida mediante bloqueo de archivo en el volumen local (Linux/macOS). Se responde 429 si hay otra en curso. Hasta **10 archivos sin publicar por usuario** y **5 GB de staging global**, configurables mediante `MAX_PENDING_PER_USER` y `MAX_STAGING_BYTES`.
- Antes de recibir un archivo se reserva espacio para el máximo permitido, tanto en la cuota de staging como en disco. Se exige espacio libre para dos copias del máximo más `MIN_FREE_DISK_BYTES` (por defecto 1 GB), para cubrir el spool multipart y la copia local. Las peticiones inactivas durante 30 segundos al leer el cuerpo se interrumpen.
- La autenticación y el control de origen se ejecutan antes del parser. Los formularios administrativos tienen un máximo de 64 KiB; la subida permite un archivo, seis campos de texto y 16 KiB por campo. Los límites también cuentan cuerpos sin `Content-Length`. Los errores de copia o persistencia limpian el archivo parcial.
- Cookie `HttpOnly`, `SameSite=Lax` para permitir el retorno desde Google, `Secure` cuando `BASE_URL` es HTTPS. En producción **BASE_URL debe ser el dominio público con HTTPS**. La sesión caduca a las 24 horas desde su emisión; `SESSION_MAX_AGE_SECONDS` permite ajustarla entre 5 minutos y 14 días. La identidad sigue vinculada al email. El logout borra la cookie del navegador; la revocación centralizada de copias robadas sigue fuera de este cambio.
- Protección CSRF mediante comparación estricta de `Origin` (o `Referer` si falta) con el origen configurado, nunca con `Host`. Se rechazan escrituras sin ambos encabezados. Los clientes automatizados necesitan enviar `Origin: <BASE_URL>`, además de una sesión válida. Cerrar sesión ahora es **POST /logout**.

Las subidas del propietario pasan a `procesando` y se publican automáticamente. Un fallo queda como `error_publicacion`, visible en **Panel → Tus publicaciones**, donde se puede reintentar o descartar. Las de amigos siguen en `pendiente` para aprobación. Al arrancar, las publicaciones interrumpidas y los pendientes antiguos del propietario pasan a error recuperable. **Mantener un solo worker/réplica**, como en el Dockerfile actual: esta recuperación al arranque no está diseñada para varias réplicas iniciándose mientras hay trabajos activos. No se necesita una migración del esquema de SQLite.

**Cloudflare:** el límite de la app no aumenta el del proxy. Free/Pro admiten normalmente 100 MB por petición y Business 200 MB; los archivos mayores necesitan otro flujo de subida (por partes o directo a GCS con autorización), todavía no implementado. Ver [límites de Cloudflare](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/).

## Pruebas

```bash
./venv/bin/python -m unittest discover -s tests -v
```

Las pruebas usan SQLite y archivos temporales; simulan las llamadas de publicación a Google Cloud. Cubren permisos, CSRF, sesiones, tamaños, formatos, cuotas, limpieza y publicación/reintentos del propietario. No publican libros ni modifican la base de datos real.

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
