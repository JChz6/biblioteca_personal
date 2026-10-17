"""Checks before form parsing, plus bounded request bodies."""
import asyncio
import fcntl
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.db.models import PendingUpload, User
from app.db.session import SessionLocal


def _origin(url):
    try:
        parts = urlsplit(url)
        if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
            return None
        return (parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80))
    except ValueError:
        return None


def _authorize_write(scope):
    email = scope.get('session', {}).get('email')
    with SessionLocal() as db:
        user = db.get(User, email) if email else None
        if user is None or not user.active:
            raise HTTPException(401, 'Inicia sesión antes de enviar el formulario.')
        if scope['path'].startswith('/panel') and user.role != 'owner':
            raise HTTPException(403, 'No tienes permiso para realizar esta acción.')


def check_disk_capacity(email):
    settings = get_settings()
    with SessionLocal() as db:
        count = db.query(PendingUpload).filter(
            PendingUpload.uploader_email == email,
            PendingUpload.status.in_(['pendiente', 'procesando', 'error_publicacion']),
        ).count()
        if count >= settings.max_pending_per_user:
            raise HTTPException(429, 'Has alcanzado el límite de archivos sin publicar.')
    pending = Path(settings.pending_dir)
    used = sum(p.stat().st_size for p in pending.iterdir() if p.is_file())
    if used + settings.max_upload_bytes > settings.max_staging_bytes:
        raise HTTPException(507, 'El espacio para subidas está lleno. Revisa los archivos pendientes.')
    # Reserve room for both the multipart spool and the staging copy, even on one volume.
    reserve = 2 * settings.max_upload_bytes + settings.min_free_disk_bytes
    for folder in {str(pending), tempfile.gettempdir()}:
        if shutil.disk_usage(folder).free < reserve:
            raise HTTPException(507, 'No hay espacio suficiente para recibir otro archivo.')


class FormSecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] in {'GET', 'HEAD', 'OPTIONS'}:
            return await self.app(scope, receive, send)
        settings = get_settings()
        headers = Headers(scope=scope)
        source = headers.get('origin')
        if source is None:
            source = headers.get('referer', '')
        # Compare against configuration, never against an attacker-supplied Host header.
        if _origin(source) is None or _origin(source) != _origin(settings.base_url):
            return await JSONResponse({'detail': 'Origen del formulario no permitido.'}, 403)(scope, receive, send)
        lock = None
        try:
            await run_in_threadpool(_authorize_write, scope)
            is_upload = scope['path'] == '/subir'
            if is_upload:
                # Shared by workers on this host; automatically released on process exit.
                lock = (Path(settings.pending_dir).parent / '.upload.lock').open('a')
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise HTTPException(429, 'Hay otra subida en curso. Inténtalo nuevamente en unos momentos.')
                await run_in_threadpool(check_disk_capacity, scope['session']['email'])
            limit = settings.max_upload_bytes + 65536 if is_upload else 65536
            async def receive_with_timeout():
                try:
                    return await asyncio.wait_for(receive(), timeout=30)
                except TimeoutError:
                    raise HTTPException(408, 'La recepción del formulario estuvo inactiva demasiado tiempo.')

            bounded = RequestBodyLimitMiddleware(self.app, max_body_size=limit)
            await bounded(scope, receive_with_timeout, send)
        except HTTPException as exc:
            await JSONResponse({'detail': exc.detail}, exc.status_code)(scope, receive, send)
        finally:
            if lock is not None:
                lock.close()
