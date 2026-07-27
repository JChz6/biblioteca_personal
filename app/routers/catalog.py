from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import require_login
from app.bigquery.catalogo import listar_catalogo
from app.db.models import Categoria, User
from app.db.session import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def catalog_view(
    request: Request,
    q: str | None = None,
    categoria: str | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    incluir_privados = user.role == "owner"
    libros = listar_catalogo(search=q, categoria=categoria or None, incluir_privados=incluir_privados)
    categorias = [c.nombre for c in db.query(Categoria).order_by(Categoria.nombre).all()]
    return templates.TemplateResponse(
        request,
        "catalog.html",
        {
            "libros": libros,
            "categorias": categorias,
            "q": q or "",
            "categoria_sel": categoria or "",
            "user": user,
        },
    )
