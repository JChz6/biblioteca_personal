import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.auth.dependencies import require_login
from app.config import get_settings
from app.db.models import Categoria, PendingUpload, User
from app.db.session import get_db
from app.services.approval import aprobar_pending_en_segundo_plano
from app.templating import templates
from app.upload_validation import ALLOWED_EXTENSIONS, save_upload, validate_book

router = APIRouter()


class BookFields(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    autor: str = Field(min_length=1, max_length=200)
    nuevo_titulo: str = Field(min_length=1, max_length=300)
    categoria: str = Field(min_length=1, max_length=100)
    comentarios: str = Field(default='', max_length=4000)
    privado: bool = False


@router.get('/subir')
def subir_form(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    categorias = [c.nombre for c in db.query(Categoria).order_by(Categoria.nombre).all()]
    return templates.TemplateResponse(request, 'subir.html', {
        'user': user, 'categorias': categorias,
        'allowed_extensions': ','.join(ALLOWED_EXTENSIONS),
        'max_upload_mb': get_settings().max_upload_bytes // 1_000_000,
    })


def _stage_upload(form, user, db):
    settings = get_settings()
    archivo = form.get('archivo')
    if not isinstance(archivo, UploadFile) or not archivo.filename:
        raise HTTPException(422, 'Selecciona un archivo.')
    if len(form.multi_items()) != len(form):
        raise HTTPException(422, 'El formulario contiene campos repetidos.')
    try:
        fields = BookFields.model_validate({k: v for k, v in form.items() if k != 'archivo'})
    except ValidationError:
        raise HTTPException(422, 'Revisa el título (300 caracteres), autor (200), categoría y comentarios (4000).')
    if db.get(Categoria, fields.categoria) is None:
        raise HTTPException(422, 'Selecciona una categoría existente.')
    name = Path(archivo.filename.replace('\\', '/')).name
    if len(name) > 255:
        raise HTTPException(422, 'El nombre del archivo es demasiado largo.')
    titulo_original, extension = os.path.splitext(name)
    extension = extension.lower()
    if archivo.size is None or archivo.size == 0:
        raise HTTPException(422, 'El archivo está vacío.')
    if archivo.size > settings.max_upload_bytes:
        raise HTTPException(413, 'El archivo supera el tamaño máximo permitido.')
    validate_book(archivo.file, extension)
    pending = PendingUpload(
        id=uuid.uuid4().hex[:12], titulo_original=titulo_original, extension=extension,
        uploader_email=user.email, status='procesando' if user.role == 'owner' else 'pendiente',
        local_file_path='', **fields.model_dump(),
    )
    dest_path = Path(settings.pending_dir) / f'{pending.id}{extension}'
    save_upload(archivo.file, dest_path, settings.max_upload_bytes)
    try:
        pending.local_file_path = str(dest_path)
        db.add(pending)
        db.commit()
    except Exception:
        db.rollback()
        dest_path.unlink(missing_ok=True)
        raise
    return pending.id


@router.post('/subir')
async def subir_submit(request: Request, background_tasks: BackgroundTasks,
                       user: User = Depends(require_login), db: Session = Depends(get_db)):
    # Authentication and middleware quotas run before any multipart parsing.
    async with request.form(max_files=1, max_fields=6, max_part_size=16_384) as form:
        pending_id = await run_in_threadpool(_stage_upload, form, user, db)
    if user.role == 'owner':
        background_tasks.add_task(aprobar_pending_en_segundo_plano, pending_id, user.email)
        return RedirectResponse(url='/?msg=procesando', status_code=303)
    return RedirectResponse(url='/subir?msg=pendiente', status_code=303)
