from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_owner
from app.db.models import Categoria, PendingUpload, User
from app.db.session import get_db
from app.services.approval import aprobar_pending, aprobar_pending_en_segundo_plano, rechazar_pending
from app.templating import templates

router = APIRouter()


@router.get("/panel/{pending_id}/archivo")
def ver_archivo_pendiente(pending_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    pending = db.get(PendingUpload, pending_id)
    if pending is None or not pending.local_file_path:
        raise HTTPException(status_code=404)
    return FileResponse(pending.local_file_path, filename=f"{pending.titulo_original}{pending.extension}")


@router.get("/panel")
def panel(request: Request, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    pendientes = (
        db.query(PendingUpload)
        .filter(PendingUpload.status == "pendiente")
        .order_by(PendingUpload.created_at)
        .all()
    )
    publicaciones = (
        db.query(PendingUpload)
        .filter(PendingUpload.status.in_(["procesando", "error_publicacion"]))
        .order_by(PendingUpload.created_at).all()
    )
    categorias = [c.nombre for c in db.query(Categoria).order_by(Categoria.nombre).all()]
    usuarios = db.query(User).order_by(User.role.desc(), User.email).all()
    return templates.TemplateResponse(
        request,
        "panel.html",
        {"user": user, "pendientes": pendientes, "categorias": categorias, "usuarios": usuarios, "publicaciones": publicaciones},
    )


@router.post("/panel/{pending_id}/aprobar")
def aprobar(
    pending_id: str,
    autor: str = Form(..., max_length=200),
    nuevo_titulo: str = Form(..., max_length=300),
    categoria: str = Form(..., max_length=100),
    comentarios: str = Form("", max_length=4000),
    privado: bool = Form(False),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    if db.get(Categoria, categoria) is None:
        raise HTTPException(422, "Selecciona una categoría existente.")
    pending = db.get(PendingUpload, pending_id)
    if pending is not None and pending.status == "pendiente":
        pending.autor = autor
        pending.nuevo_titulo = nuevo_titulo
        pending.categoria = categoria
        pending.comentarios = comentarios
        pending.privado = privado
        db.add(pending)
        db.commit()
        aprobar_pending(db, pending, aprobado_por=user.email)
    return RedirectResponse(url="/panel", status_code=303)


@router.post("/panel/{pending_id}/rechazar")
def rechazar(
    pending_id: str,
    motivo: str = Form("", max_length=1000),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    pending = db.get(PendingUpload, pending_id)
    if pending is not None and pending.status in {"pendiente", "error_publicacion"}:
        rechazar_pending(db, pending, rechazado_por=user.email, motivo=motivo)
    return RedirectResponse(url="/panel", status_code=303)


@router.post("/panel/usuarios/agregar")
def agregar_usuario(
    email: str = Form(..., max_length=320),
    display_name: str = Form("", max_length=200),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    existente = db.get(User, email)
    if existente is None:
        db.add(User(email=email, role="friend", display_name=display_name, added_by=user.email))
        db.commit()
    return RedirectResponse(url="/panel", status_code=303)


@router.post("/panel/usuarios/{email}/desactivar")
def desactivar_usuario(email: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    objetivo = db.get(User, email)
    if objetivo is not None and objetivo.role != "owner":
        objetivo.active = False
        db.add(objetivo)
        db.commit()
    return RedirectResponse(url="/panel", status_code=303)


@router.post("/panel/usuarios/{email}/reactivar")
def reactivar_usuario(email: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    objetivo = db.get(User, email)
    if objetivo is not None:
        objetivo.active = True
        db.add(objetivo)
        db.commit()
    return RedirectResponse(url="/panel", status_code=303)


@router.post("/panel/categorias/agregar")
def agregar_categoria(nombre: str = Form(..., max_length=100), user: User = Depends(require_owner), db: Session = Depends(get_db)):
    nombre = nombre.strip()
    if nombre and db.get(Categoria, nombre) is None:
        db.add(Categoria(nombre=nombre))
        db.commit()
    return RedirectResponse(url="/panel", status_code=303)


@router.post("/panel/{pending_id}/reintentar")
def reintentar_publicacion(pending_id: str, background_tasks: BackgroundTasks,
                          user: User = Depends(require_owner), db: Session = Depends(get_db)):
    pending = db.get(PendingUpload, pending_id)
    if pending is None or pending.status != "error_publicacion":
        raise HTTPException(409, "Esta publicación no está pendiente de reintento.")
    pending.status = "procesando"
    db.commit()
    background_tasks.add_task(aprobar_pending_en_segundo_plano, pending.id, user.email)
    return RedirectResponse(url="/panel", status_code=303)
