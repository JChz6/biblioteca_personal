import os
import hashlib
import shutil
import time
import pandas as pd
import pytz
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from datetime import datetime

# Google libs
from google.cloud import storage
from google.cloud import bigquery
from google.oauth2 import service_account

# ------------- CONFIG -------------
SERVICE_ACCOUNT_FILE = "E:/Biblioteca_personal/agente_drive_gcs_bq.json"
PROJECT_ID = "big-query-406221"
BQ_DATASET = "biblioteca_personal"
BQ_TABLE = "catalogo"
GCS_BUCKET = "biblioteca_personal"
CSV_IN = "E:/Biblioteca_personal/catalogo_biblioteca.csv"
DESTINO_BASE_LOCAL = "E:/Biblioteca_personal"

RENOMBRAR_LOCAL = False
SUBIR_GCS = True

ACTUALIZAR_BIGQUERY = True
BQ_BATCH_SIZE = False
# -----------------------------------
utc_minus_5 = pytz.timezone('America/Lima')

# ----------------- Inicialización de clientes -----------------
credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)
storage_client = storage.Client(credentials=credentials, project=PROJECT_ID)
bq_client = bigquery.Client(credentials=credentials, project=PROJECT_ID)

# ----------------- Helpers -----------------
def generar_id(row):
    ruta = str(row.get("ruta_compleata") or row.get("ruta_local") or "")
    s = f"{ruta}-{row.get('nuevo_titulo')}-{row.get('autor')}-{row.get('categoria')}-{row.get('extension')}"
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]


def md5_archivo(path, chunk_size=8192):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()

def safe_filename(s):
    s = str(s or "").strip()
    for c in ['/', '\\', ':', '*', '?', '¿', '"', '<', '>', '|']:
        s = s.replace(c, '')
    return s.replace('\n', ' ').replace('\r', '')

def upload_to_gcs(local_path, bucket_name, dest_path):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(dest_path)
    blob.upload_from_filename(local_path)
    return f"gs://{bucket_name}/{dest_path}"


def construir_urls_gcs(gcs_uri):
    if not gcs_uri:
        return "", ""
    blob_path = gcs_uri.replace(f"gs://{GCS_BUCKET}/", "")
    url_publica = f"https://storage.googleapis.com/{GCS_BUCKET}/{blob_path}"
    url_autenticada = f"https://storage.cloud.google.com/{GCS_BUCKET}/{blob_path}"
    return url_publica, url_autenticada


def copiar_archivo_seguro(src, dest):
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.isfile(dest):
            ts = int(time.time())
            base, ext = os.path.splitext(dest)
            dest = f"{base}_{ts}{ext}"
        shutil.copy2(src, dest)
        return dest
    except Exception as e:
        print(f"[ERROR COPY] {src} -> {dest}: {e}")
        return None
    

# ----------------- BigQuery helpers -----------------
def preparar_dataframe_para_bigquery(df):
    df_bq = pd.DataFrame({
        "id": df["id"],
        "titulo_original": df.get("titulo_original", ""),
        "autor": df["autor"],
        "nuevo_titulo": df["nuevo_titulo"],
        "extension": df["extension"],
        "categoria": df["categoria"],
        "ruta_completa": df["ruta_completa"],
        "fecha_creacion": pd.to_datetime(df["fecha_creacion"], errors="coerce"),
        "fecha_modificacion": pd.to_datetime(df["fecha_modificacion"], errors="coerce"),
        "comentarios": df.get("comentarios"),
        "ruta_local": df["ruta_local"],
        "uri_gcs": df.get("uri_gcs"),
        "url_publica": df.get("url_publica"),
        "url_autenticada": df.get("url_autenticada"),
        "privado": df.get("privado").astype(str).str.lower().isin(["true", "1", "yes", "y", "t"]),
        "fecha_carga": df["fecha_carga"].dt.tz_localize(None)
    })
    return df_bq

def upsert_bigquery(df_chunk, dataset_id, table_id):
    """
    Sube df_chunk a una tabla temporal y hace MERGE con la tabla final.
    df_chunk debe ya estar preparado (preparar_dataframe_para_bigquery).
    """
    df_bq = preparar_dataframe_para_bigquery(df_chunk)
    timestamp = int(time.time())
    temp_table_suffix = f"_temp_upsert_{timestamp}"
    temp_table_full = f"{PROJECT_ID}.{dataset_id}.{BQ_TABLE}{temp_table_suffix}"

    job_config = bigquery.LoadJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    # Crea y carga a la tabla temporal
    load_job = bq_client.load_table_from_dataframe(df_bq, temp_table_full, job_config=job_config)
    load_job.result()

    full_table = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    merge_sql = f"""
    MERGE `{full_table}` T
    USING `{temp_table_full}` S
    ON T.id = S.id
    WHEN MATCHED THEN
    UPDATE SET
        titulo_original = S.titulo_original,
        autor = S.autor,
        nuevo_titulo = S.nuevo_titulo,
        extension = S.extension,
        categoria = S.categoria,
        ruta_completa = S.ruta_completa,
        fecha_creacion = S.fecha_creacion,
        fecha_modificacion = S.fecha_modificacion,
        comentarios = S.comentarios,
        ruta_local = S.ruta_local,
        uri_gcs = S.uri_gcs,
        url_publica = S.url_publica,
        url_autenticada = S.url_autenticada,
        privado = S.privado,
        fecha_carga = CURRENT_DATETIME('America/Lima')
    WHEN NOT MATCHED THEN
    INSERT (
        id, titulo_original, autor, nuevo_titulo, extension, categoria, ruta_completa,
        fecha_creacion, fecha_modificacion, comentarios, ruta_local, uri_gcs, url_publica, url_autenticada, privado, fecha_carga
    )
    VALUES (
        S.id, S.titulo_original, S.autor, S.nuevo_titulo, S.extension, S.categoria, S.ruta_completa,
        S.fecha_creacion, S.fecha_modificacion, S.comentarios, S.ruta_local, S.uri_gcs, S.url_publica, S.url_autenticada, S.privado,
        CURRENT_DATETIME('America/Lima')
    )
    """

    bq_client.query(merge_sql).result()

    # Borrar tabla temporal
    bq_client.delete_table(temp_table_full, not_found_ok=True)
    print(f"[BIGQUERY] Upsert completado ({len(df_bq)} filas) en {dataset_id}.{table_id}")

# ----------------- Procesamiento principal -----------------
def construir_dataframe_catalogo(csv_in):
    """
    Lee CSV y construye el DataFrame inicial con columnas y metadatos básicos.
    """
    df = pd.read_csv(csv_in, dtype=str).fillna("")

    required_cols = ["titulo_original", "autor", "nuevo_titulo", "categoria", "ruta_completa"]
    for c in required_cols:
        if c not in df.columns:
            raise ValueError(f"Falta columna requerida: {c}")

    # Guarda la ruta original antes de modificarla
    df["ruta_local"] = df["ruta_local"] = DESTINO_BASE_LOCAL + "/" + df["categoria"] + "/" + df["nuevo_titulo"] + " - " + df["autor"] + df["extension"]

    # Genera id
    df["id"] = df.apply(generar_id, axis=1)
    df["extension"] = df["ruta_completa"].apply(lambda p: os.path.splitext(str(p))[1].lower())

    # Fechas de creación y modificación de archivos
    fecha_creacion, fecha_mod = [], []
    for ruta in df["ruta_completa"]:
        if os.path.isfile(ruta):
            try:
                fecha_creacion.append(datetime.fromtimestamp(os.path.getctime(ruta)).isoformat())
                fecha_mod.append(datetime.fromtimestamp(os.path.getmtime(ruta)).isoformat())
            except Exception as e:
                print(f"[WARN] Error leyendo fechas: {ruta}: {e}")
                fecha_creacion.append("")
                fecha_mod.append("")
        else:
            fecha_creacion.append("")
            fecha_mod.append("")

    df["fecha_creacion"] = fecha_creacion
    df["fecha_modificacion"] = fecha_mod
    df["uri_gcs"] = ""

    df['fecha_carga'] = datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None)
    df['fecha_carga'] = pd.to_datetime(df['fecha_carga'])
    
    df = df[~df['nuevo_titulo'].str.strip().str.upper().eq('BORRAR')]
    

    return df





def procesar_archivos_catalogo(df):
    """
    Procesa el DataFrame: renombrado de archivos, subida a GCS y carga a BigQuery.
    """
    if RENOMBRAR_LOCAL:
        os.makedirs(DESTINO_BASE_LOCAL, exist_ok=True)

    for idx, row in df.iterrows():
        ruta = row["ruta_completa"]
        nombre = row["nuevo_titulo"]

        # Saltar si marcado BORRAR
        if str(nombre).strip().upper() == "BORRAR":
            continue

        if not os.path.isfile(ruta):
            print(f"[SKIP] No encontrado: {ruta}")
            continue

        # Formateo Title-case
        titulo_format = str(row["nuevo_titulo"]).strip().title()
        autor_format = str(row["autor"]).strip().title()

        titulo_safe = safe_filename(titulo_format)
        autor_safe = safe_filename(autor_format)
        categoria_dir = safe_filename(row["categoria"])
        nueva_basename = f"{titulo_safe} - {autor_safe}{row['extension']}"

        local_to_upload = ruta
        if RENOMBRAR_LOCAL:
            nueva_dir = os.path.join(DESTINO_BASE_LOCAL, categoria_dir)
            nueva_ruta_local = os.path.join(nueva_dir, nueva_basename)
            local_to_upload = copiar_archivo_seguro(ruta, nueva_ruta_local)
            if local_to_upload:
                df.at[idx, "ruta_completa"] = str(Path(local_to_upload).resolve())
                df.at[idx, "nuevo_titulo"] = titulo_format
                df.at[idx, "autor"] = autor_format
                print(f"[LOCAL] Copiado: {titulo_format} -> {local_to_upload}")

        if SUBIR_GCS and local_to_upload:
            dest_blob_path = f"{categoria_dir}/{row['id']}_{nueva_basename}"
            try:
                gcs_uri = upload_to_gcs(local_to_upload, GCS_BUCKET, dest_blob_path)
                df.at[idx, "uri_gcs"] = gcs_uri

                # Generar URLs
                public_url, auth_url = construir_urls_gcs(gcs_uri)
                df.at[idx, "url_publica"] = public_url
                df.at[idx, "url_autenticada"] = auth_url

                print(f"[GCS] Subido: {gcs_uri}")
            except Exception as e:
                print(f"[ERROR GCS] {e}")


    # Carga a BigQuery
    if ACTUALIZAR_BIGQUERY:
        try:
            if BQ_BATCH_SIZE and isinstance(BQ_BATCH_SIZE, int) and BQ_BATCH_SIZE > 0:
                total = len(df)
                for start in range(0, total, BQ_BATCH_SIZE):
                    chunk = df.iloc[start:start + BQ_BATCH_SIZE]
                    upsert_bigquery(chunk, BQ_DATASET, BQ_TABLE)
                    print(f"[BQ] Lote subido {start} - {start + len(chunk) - 1}")
            else:
                upsert_bigquery(df, BQ_DATASET, BQ_TABLE)
        except Exception as e:
            print(f"[ERROR BQ] {e}")

    # Guardar CSV actualizado
    out_csv = f"E:/Biblioteca_personal/catalogo_actualizado.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"✅ Catálogo actualizado guardado en: {out_csv}")




if __name__ == "__main__":
    df_catalogo = construir_dataframe_catalogo(CSV_IN)
    procesar_archivos_catalogo(df_catalogo)
