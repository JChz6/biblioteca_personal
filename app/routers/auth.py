from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.oauth import oauth
from app.config import get_settings
from app.db.models import User
from app.db.session import SessionLocal

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.get("/auth/google")
async def auth_google(request: Request):
    settings = get_settings()
    redirect_uri = f"{settings.base_url}/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo or not userinfo.get("email"):
        return HTMLResponse("No se pudo obtener el email de Google.", status_code=400)

    email = userinfo["email"].lower()
    with SessionLocal() as db:
        user = db.get(User, email)

    if user is None or not user.active:
        return templates.TemplateResponse(
            request, "no_autorizado.html", {"email": email}, status_code=403
        )

    request.session["email"] = email
    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")
