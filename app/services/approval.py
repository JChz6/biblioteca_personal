import os
from datetime import datetime

from sqlalchemy.orm import Session

from app.bigquery.catalogo import upsert_libro_aprobado
from app.db.models import PendingUpload
from app.gcs.storage import construir_urls_gcs, delete_blob, safe_filename, upload_to_gcs


def aprobar_pending(db: Session, pending: PendingUpload, aprobado_por: str) -> str:
    """
    Sube el archivo en staging a GCS, hace upsert a BigQuery, marca el pending
    como aprobado y borra el archivo local. Devuelve el id del libro aprobado.
    """
    titulo_format = pending.nuevo_titulo.strip().title()
    autor_format = pending.autor.strip().title()
    titulo_safe = safe_filename(titulo_format)
    autor_safe = safe_filename(autor_format)
    categoria_dir = safe_filename(pending.categoria)
    nueva_basename = f"{titulo_safe} - {autor_safe}{pending.extension}"
    dest_blob_path = f"{categoria_dir}/{pending.id}_{nueva_basename}"

    gcs_uri = upload_to_gcs(pending.local_file_path, dest_blob_path)

    try:
        url_publica, url_autenticada = construir_urls_gcs(gcs_uri)
        ahora = datetime.now()
        row = {
            "id": pending.id,
            "titulo_original": pending.titulo_original,
            "autor": autor_format,
            "nuevo_titulo": titulo_format,
            "extension": pending.extension,
            "categoria": pending.categoria,
            "ruta_completa": pending.local_file_path,
            "fecha_creacion": ahora,
            "fecha_modificacion": ahora,
            "comentarios": pending.comentarios,
            "ruta_local": "",
            "uri_gcs": gcs_uri,
            "url_publica": url_publica,
            "url_autenticada": url_autenticada,
            "privado": pending.privado,
            "subido_por": pending.uploader_email,
            "aprobado_por": aprobado_por,
            "fecha_aprobacion": ahora,
        }
        upsert_libro_aprobado(row)
    except Exception:
        # El archivo ya subió a GCS pero no quedó registrado en BigQuery: lo borramos
        # para no dejar un blob huérfano. El pending queda en "pendiente" para reintentar.
        delete_blob(gcs_uri)
        raise

    if os.path.isfile(pending.local_file_path):
        os.remove(pending.local_file_path)

    pending.status = "aprobado"
    pending.reviewed_at = ahora
    pending.reviewed_by = aprobado_por
    pending.catalogo_id = pending.id
    db.add(pending)
    db.commit()
    return pending.id


def rechazar_pending(db: Session, pending: PendingUpload, rechazado_por: str, motivo: str = "") -> None:
    if os.path.isfile(pending.local_file_path):
        os.remove(pending.local_file_path)

    pending.status = "rechazado"
    pending.reviewed_at = datetime.now()
    pending.reviewed_by = rechazado_por
    pending.rejection_reason = motivo
    db.add(pending)
    db.commit()
