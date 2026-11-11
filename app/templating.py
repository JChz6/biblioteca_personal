import hashlib
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app import i18n


def _compute_static_version() -> str:
    """
    Hash corto del CSS + favicon, usado como ?v= en los <link> de static/.
    Cambia automáticamente cuando cambia el contenido, así Cloudflare (u otro
    cache) nunca sirve una versión vieja bajo la misma URL después de un deploy.
    """
    static_dir = Path(__file__).resolve().parent / "static"
    digest = hashlib.md5()
    for name in ("style.css", "app.js", "library-icon.svg", "library-touch-icon.png"):
        try:
            digest.update((static_dir / name).read_bytes())
        except FileNotFoundError:
            continue
    return digest.hexdigest()[:8]


templates = Jinja2Templates(directory="app/templates")
templates.env.globals["static_version"] = _compute_static_version()
i18n.install(templates.env)
