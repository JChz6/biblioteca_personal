from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db


class NotAuthenticated(Exception):
    """El usuario no tiene sesión válida — debe pasar por /login."""


class NotAuthorized(Exception):
    """El usuario tiene sesión pero no el rol requerido (ej. no es owner)."""


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    email = request.session.get("email")
    if not email:
        return None
    user = db.get(User, email)
    if user is None or not user.active:
        return None
    return user


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise NotAuthenticated()
    return user


def require_owner(user: User = Depends(require_login)) -> User:
    if user.role != "owner":
        raise NotAuthorized()
    return user
