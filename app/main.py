from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth.dependencies import NotAuthenticated, NotAuthorized
from app.config import get_settings
from app.db.session import init_db
from app.routers import admin, auth, catalog, download, upload

settings = get_settings()

app = FastAPI(title="Biblioteca Personal")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.exception_handler(NotAuthenticated)
async def handle_not_authenticated(request: Request, exc: NotAuthenticated) -> RedirectResponse:
    return RedirectResponse(url="/login")


@app.exception_handler(NotAuthorized)
async def handle_not_authorized(request: Request, exc: NotAuthorized) -> HTMLResponse:
    return HTMLResponse("<h1>403</h1><p>No tienes permiso para ver esta página.</p>", status_code=403)


app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(download.router)
app.include_router(upload.router)
app.include_router(admin.router)
