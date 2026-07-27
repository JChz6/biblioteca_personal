import math

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import require_login
from app.bigquery.catalogo import agrupar_por_obra, listar_catalogo
from app.db.models import Categoria, User
from app.db.session import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 24


def _pagination_window(current: int, total: int, radius: int = 2) -> list[int | None]:
    if total <= 1:
        return [1] if total == 1 else []
    pages = set(range(1, min(3, total) + 1))
    pages.update(range(max(1, current - radius), min(total, current + radius) + 1))
    pages.update(range(max(1, total - 2), total + 1))
    ordered = sorted(pages)
    window: list[int | None] = []
    previous = None
    for p in ordered:
        if previous is not None and p - previous > 1:
            window.append(None)
        window.append(p)
        previous = p
    return window


@router.get("/")
def catalog_view(
    request: Request,
    q: str | None = None,
    categoria: str | None = None,
    page: int = 1,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    incluir_privados = user.role == "owner"
    libros = listar_catalogo(search=q, categoria=categoria or None, incluir_privados=incluir_privados)
    grupos = agrupar_por_obra(libros)
    categorias = [c.nombre for c in db.query(Categoria).order_by(Categoria.nombre).all()]

    total = len(grupos)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    inicio = (page - 1) * PAGE_SIZE
    libros_pagina = grupos[inicio: inicio + PAGE_SIZE]

    return templates.TemplateResponse(
        request,
        "catalog.html",
        {
            "libros": libros_pagina,
            "categorias": categorias,
            "q": q or "",
            "categoria_sel": categoria or "",
            "user": user,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "page_window": _pagination_window(page, total_pages),
        },
    )
