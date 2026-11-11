from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import i18n
from app.auth.oauth import oauth
from app.config import get_settings
from app.db.models import User
from app.db.session import SessionLocal
from app.templating import templates

router = APIRouter()


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
        return HTMLResponse(i18n.translate(i18n.get_lang(request), "google_email_fail"), status_code=400)

    email = userinfo["email"].lower()
    with SessionLocal() as db:
        user = db.get(User, email)

    if user is None or not user.active:
        return templates.TemplateResponse(
            request, "no_autorizado.html", {"email": email}, status_code=403
        )

    request.session["email"] = email
    return RedirectResponse(url="/")


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.get("/idioma/{code}")
async def set_language(request: Request, code: str, next: str = "/"):
    # Solo rutas internas: evita redirecciones abiertas (//evil.com, /\evil.com).
    if not next.startswith("/") or next.startswith("//") or next.startswith("/\\"):
        next = "/"
    response = RedirectResponse(url=next, status_code=303)
    if code in i18n.LANGS:
        response.set_cookie(
            i18n.COOKIE_NAME, code, max_age=60 * 60 * 24 * 365, samesite="lax",
            secure=get_settings().base_url.lower().startswith("https://"),
        )
    return response
