from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_owner
from app.db.models import Categoria, PendingUpload, User
from app.db.session import get_db
from app.services.approval import aprobar_pending, rechazar_pending
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
    categorias = [c.nombre for c in db.query(Categoria).order_by(Categoria.nombre).all()]
    usuarios = db.query(User).order_by(User.role.desc(), User.email).all()
    return templates.TemplateResponse(
        request,
        "panel.html",
        {"user": user, "pendientes": pendientes, "categorias": categorias, "usuarios": usuarios},
    )


@router.post("/panel/{pending_id}/aprobar")
def aprobar(
    pending_id: str,
    autor: str = Form(...),
    nuevo_titulo: str = Form(...),
    categoria: str = Form(...),
    comentarios: str = Form(""),
    privado: bool = Form(False),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
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
    motivo: str = Form(""),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    pending = db.get(PendingUpload, pending_id)
    if pending is not None and pending.status == "pendiente":
        rechazar_pending(db, pending, rechazado_por=user.email, motivo=motivo)
    return RedirectResponse(url="/panel", status_code=303)


@router.post("/panel/usuarios/agregar")
def agregar_usuario(
    email: str = Form(...),
    display_name: str = Form(""),
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
def agregar_categoria(nombre: str = Form(...), user: User = Depends(require_owner), db: Session = Depends(get_db)):
    nombre = nombre.strip()
    if nombre and db.get(Categoria, nombre) is None:
        db.add(Categoria(nombre=nombre))
        db.commit()
    return RedirectResponse(url="/panel", status_code=303)
