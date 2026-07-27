import os
import shutil

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import require_login
from app.config import get_settings
from app.db.models import Categoria, PendingUpload, User
from app.db.session import get_db
from app.services.approval import aprobar_pending

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/subir")
def subir_form(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    categorias = [c.nombre for c in db.query(Categoria).order_by(Categoria.nombre).all()]
    return templates.TemplateResponse(request, "subir.html", {"user": user, "categorias": categorias})


@router.post("/subir")
def subir_submit(
    request: Request,
    archivo: UploadFile,
    autor: str = Form(...),
    nuevo_titulo: str = Form(...),
    categoria: str = Form(...),
    comentarios: str = Form(""),
    privado: bool = Form(False),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    settings = get_settings()

    titulo_original, extension = os.path.splitext(archivo.filename or "")
    extension = extension.lower()

    pending = PendingUpload(
        titulo_original=titulo_original,
        autor=autor,
        nuevo_titulo=nuevo_titulo,
        extension=extension,
        categoria=categoria,
        comentarios=comentarios,
        privado=privado,
        uploader_email=user.email,
        local_file_path="",  # se completa abajo, ya con el id generado
    )
    db.add(pending)
    db.flush()  # asigna pending.id sin cerrar la transacción

    dest_path = os.path.join(settings.pending_dir, f"{pending.id}{extension}")
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(archivo.file, f)
    pending.local_file_path = dest_path
    db.commit()

    if user.role == "owner":
        aprobar_pending(db, pending, aprobado_por=user.email)
        return RedirectResponse(url="/?msg=subido", status_code=303)

    return RedirectResponse(url="/subir?msg=pendiente", status_code=303)
