from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import i18n
from app.auth.dependencies import NotAuthenticated, NotAuthorized
from app.bigquery.catalogo import get_catalogo
from app.config import get_settings
from app.security import FormSecurityMiddleware
from app.db.session import init_db
from app.routers import admin, auth, catalog, download, upload

settings = get_settings()

app = FastAPI(title="Biblioteca Personal")
app.add_middleware(FormSecurityMiddleware)
# Session must wrap form security so the verified session is available before parsing.
app.add_middleware(
    SessionMiddleware, secret_key=settings.session_secret_key,
    https_only=settings.base_url.lower().startswith("https://"),
    same_site="lax", max_age=settings.session_max_age_seconds,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    try:
        get_catalogo()  # precalienta el cache para que el primer request no pague la consulta a BigQuery
    except Exception:
        pass  # si falla (credenciales aún no listas, etc.) el primer request lo reintenta


@app.exception_handler(NotAuthenticated)
async def handle_not_authenticated(request: Request, exc: NotAuthenticated) -> RedirectResponse:
    return RedirectResponse(url="/login")


@app.exception_handler(NotAuthorized)
async def handle_not_authorized(request: Request, exc: NotAuthorized) -> HTMLResponse:
    message = i18n.translate(i18n.get_lang(request), "forbidden")
    return HTMLResponse(f"<h1>403</h1><p>{message}</p>", status_code=403)


app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(download.router)
app.include_router(upload.router)
app.include_router(admin.router)
