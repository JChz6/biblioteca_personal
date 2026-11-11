import math

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import require_login
from app.bigquery.catalogo import agrupar_por_obra, contar_por_autor, contar_por_categoria, listar_catalogo, ordenar_grupos
from app.db.models import Categoria, User
from app.db.session import get_db
from app.templating import templates
from app.text_utils import alphabetical_key as _alphabetical_key, initial_letter as _author_initial

router = APIRouter()

PAGE_SIZE = 24
ORDEN_VALIDOS = {"titulo", "autor", "fecha"}


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
    autor: str | None = None,
    orden: str = "fecha",
    page: int = 1,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if orden not in ORDEN_VALIDOS:
        orden = "fecha"
    incluir_privados = user.role == "owner"
    libros = listar_catalogo(
        search=q, categoria=categoria or None, autor=autor or None, incluir_privados=incluir_privados
    )
    grupos = ordenar_grupos(agrupar_por_obra(libros), orden)
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
            "autores": sorted(contar_por_autor(incluir_privados=incluir_privados), key=str.casefold),
            "q": q or "",
            "categoria_sel": categoria or "",
            "autor_sel": autor or "",
            "orden": orden,
            "user": user,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "page_window": _pagination_window(page, total_pages),
        },
    )


@router.get("/autores")
def autores_view(request: Request, user: User = Depends(require_login)):
    incluir_privados = user.role == "owner"
    conteo = contar_por_autor(incluir_privados=incluir_privados)
    autores = sorted(
        ({"nombre": nombre, "total": total} for nombre, total in conteo.items()),
        key=lambda a: _alphabetical_key(a["nombre"]),
    )
    groups: dict[str, list[dict]] = {}
    for author in autores:
        groups.setdefault(_author_initial(author["nombre"]), []).append(author)
    letters = sorted(groups, key=lambda letter: (letter == "#", _alphabetical_key(letter)))
    return templates.TemplateResponse(request, "autores.html", {
        "user": user, "autores": autores,
        "grupos_autores": [{"letra": letter, "autores": groups[letter]} for letter in letters],
    })


@router.get("/categorias")
def categorias_view(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    incluir_privados = user.role == "owner"
    conteo = contar_por_categoria(incluir_privados=incluir_privados)
    nombres = [c.nombre for c in db.query(Categoria).order_by(Categoria.nombre).all()]
    categorias = [{"nombre": n, "total": conteo.get(n, 0)} for n in sorted(nombres, key=_alphabetical_key)]
    return templates.TemplateResponse(request, "categorias.html", {"user": user, "categorias_lista": categorias})
