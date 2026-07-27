import hashlib
from pathlib import Path

from fastapi.templating import Jinja2Templates


def _compute_static_version() -> str:
    """
    Hash corto del CSS, usado como ?v= en el <link> del stylesheet. Cambia
    automáticamente cuando cambia el contenido, así Cloudflare (u otro cache)
    nunca sirve una versión vieja bajo la misma URL después de un deploy.
    """
    css_path = Path(__file__).resolve().parent / "static" / "style.css"
    try:
        return hashlib.md5(css_path.read_bytes()).hexdigest()[:8]
    except FileNotFoundError:
        return "0"


templates = Jinja2Templates(directory="app/templates")
templates.env.globals["static_version"] = _compute_static_version()
