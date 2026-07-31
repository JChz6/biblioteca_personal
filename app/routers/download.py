from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.auth.dependencies import require_login
from app.bigquery.catalogo import get_by_id
from app.db.models import User
from app.gcs.storage import safe_filename, stream_blob

router = APIRouter()


def _content_disposition(nombre_archivo: str) -> str:
    # Los headers HTTP deben ser ASCII: se manda un fallback ASCII (filename=)
    # y el nombre real en UTF-8 percent-encoded (filename*=), por RFC 5987/6266.
    ascii_fallback = nombre_archivo.encode("ascii", "ignore").decode("ascii").strip() or "libro"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(nombre_archivo)}"


@router.get("/descargar/{book_id}")
def descargar(book_id: str, user: User = Depends(require_login)):
    incluir_privados = user.role == "owner"
    libro = get_by_id(book_id, incluir_privados=incluir_privados)
    if libro is None or not libro.get("uri_gcs"):
        raise HTTPException(status_code=404, detail="Libro no encontrado")

    nombre_archivo = safe_filename(f"{libro['nuevo_titulo']} - {libro['autor']}{libro['extension']}")
    return StreamingResponse(
        stream_blob(libro["uri_gcs"]),
        media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition(nombre_archivo)},
    )
