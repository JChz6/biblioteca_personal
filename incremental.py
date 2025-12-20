#!/media/cheesus/Sandisk Celeste 2TB/Developer/biblioteca_personal/venv/bin/python  

import os
import hashlib
import shutil
import time
import pandas as pd
import pytz
from pathlib import Path
from datetime import datetime

# Google libs
from google.cloud import storage
from google.cloud import bigquery
from google.oauth2 import service_account

# ------------- CONFIG -------------
SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_ACCOUNT_FILE = SCRIPT_DIR / "agente_drive_gcs_bq.json"
PROJECT_ID = "big-query-406221"
BQ_DATASET = "biblioteca_personal"
BQ_TABLE = "catalogo"
GCS_BUCKET = "biblioteca_personal"

BASE_DIR = Path(__file__).resolve().parent

RUTA_ARCHIVOS_RAW = Path(os.environ.get(
    "BIBLIOTECA_RAW",
    BASE_DIR/".."/".."/"Biblioteca_personal"
))


#VERIFICACIONES PARA CORREGIR PROBLEMAS
'''
print(f"[CONFIG] Ruta base de archivos: {RUTA_ARCHIVOS_RAW.resolve()}")
print(f"[CONFIG] ¿Existe la ruta? {RUTA_ARCHIVOS_RAW.exists()}")
if RUTA_ARCHIVOS_RAW.exists():
    archivos = list(RUTA_ARCHIVOS_RAW.iterdir())
    print(f"[CONFIG] Contenido de la ruta ({len(archivos)} elementos):")
    for item in archivos[:20]:  # Mostrar máximo 20 elementos
        tipo = "DIR" if item.is_dir() else "FILE"
        print(f"  [{tipo}] {item.name}")
    if len(archivos) > 20:
        print(f"  ... y {len(archivos) - 20} elementos más")
else:
    print("[CONFIG] ⚠️ LA RUTA NO EXISTE")
'''
    

DESTINO_BASE_LOCAL = RUTA_ARCHIVOS_RAW

SERVICE_ACCOUNT_FILE = Path(os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    BASE_DIR/".."/".."/"Biblioteca_personal"/"service_account.json"
))

RENOMBRAR_LOCAL = True 
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
    s = f"{row.get('ruta_completa', '')}-{row.get('nuevo_titulo', '')}-{row.get('autor', '')}"
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

def mover_archivo_seguro(src, dest):
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.isfile(dest):
            ts = int(time.time())
            base, ext = os.path.splitext(dest)
            dest = f"{base}_{ts}{ext}"
        shutil.move(src, dest)
        return dest
    except Exception as e:
        print(f"[ERROR MOVE] {src} -> {dest}: {e}")
        return None

# ----------------- BigQuery helpers -----------------
def preparar_dataframe_para_bigquery(df):
    df_bq = df.copy()

    # columnas esperadas
    columnas_str = [
        "id",
        "ruta_completa",
        "ruta_local",
        "uri_gcs",
        "url_publica",
        "url_autenticada",
        "titulo_original",
        "autor",
        "nuevo_titulo",
        "extension",
        "categoria",
        "comentarios",
    ]

    for col in columnas_str:
        if col not in df_bq.columns:
            df_bq[col] = ""
        df_bq[col] = df_bq[col].astype(str)

    if "privado" in df_bq.columns:
        df_bq["privado"] = df_bq["privado"].fillna(False).astype(bool)
    else:
        df_bq["privado"] = False

    df_bq["fecha_carga"] = datetime.now(utc_minus_5)

    return df_bq


def upsert_bigquery(df_chunk, dataset_id, table_id):
    df_bq = preparar_dataframe_para_bigquery(df_chunk)
    timestamp = int(time.time())
    temp_table_suffix = f"_temp_upsert_{timestamp}"
    temp_table_full = f"{PROJECT_ID}.{dataset_id}.{table_id}{temp_table_suffix}"

    # Definir schema explícito para evitar conflictos de tipos
    schema = [
        bigquery.SchemaField("id", "STRING"),
        bigquery.SchemaField("ruta_completa", "STRING"),
        bigquery.SchemaField("ruta_local", "STRING"),
        bigquery.SchemaField("uri_gcs", "STRING"),
        bigquery.SchemaField("url_publica", "STRING"),
        bigquery.SchemaField("url_autenticada", "STRING"),
        bigquery.SchemaField("titulo_original", "STRING"),
        bigquery.SchemaField("autor", "STRING"),
        bigquery.SchemaField("nuevo_titulo", "STRING"),
        bigquery.SchemaField("extension", "STRING"),
        bigquery.SchemaField("categoria", "STRING"),
        bigquery.SchemaField("comentarios", "STRING"),
        bigquery.SchemaField("privado", "BOOLEAN"),
        bigquery.SchemaField("fecha_carga", "DATETIME"),
    ]
    
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=schema
    )
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
        comentarios = S.comentarios,
        ruta_local = S.ruta_local,
        uri_gcs = S.uri_gcs,
        url_publica = S.url_publica,
        url_autenticada = S.url_autenticada,
        privado = S.privado,
        fecha_carga = CURRENT_DATETIME('America/Lima')
    WHEN NOT MATCHED THEN
      INSERT (
        id, titulo_original, autor, nuevo_titulo, extension, categoria,
        ruta_completa, comentarios, ruta_local, uri_gcs,
        url_publica, url_autenticada, privado, fecha_carga
      )
      VALUES (
        S.id, S.titulo_original, S.autor, S.nuevo_titulo, S.extension, S.categoria,
        S.ruta_completa, S.comentarios, S.ruta_local, S.uri_gcs,
        S.url_publica, S.url_autenticada, S.privado, CURRENT_DATETIME('America/Lima')
      )
    """
    bq_client.query(merge_sql).result()
    bq_client.delete_table(temp_table_full, not_found_ok=True)
    print(f"[BIGQUERY] Upsert completado ({len(df_bq)} filas) en {dataset_id}.{table_id}")

# ----------------- Procesamiento principal -----------------
def recopilar_libros(carpeta_base):
    formatos_libros = {".pdf", ".epub", ".mobi", ".fb2", ".opf", ".cbr", ".cbz", ".txt", ".rtf"}
    datos = []
    
    # Resolver la ruta para comparaciones correctas
    carpeta_base_resolved = str(Path(carpeta_base).resolve())


    #PRINTS PARA SOLUCIONAR ERRORES
    #print(f"\n[RECOPILAR] Buscando libros en: {carpeta_base}")
    #print(f"[RECOPILAR] Ruta resuelta: {carpeta_base_resolved}")
    #print(f"[RECOPILAR] Formatos válidos: {formatos_libros}")
    
    for ruta, _, archivos in os.walk(carpeta_base_resolved):
        #print(f"\n[RECOPILAR] Explorando directorio: {ruta}")
        #print(f"[RECOPILAR] Archivos encontrados en este directorio: {len(archivos)}")
        
        if ruta != carpeta_base_resolved:
            #print(f"[RECOPILAR] ⚠️ Saltando subdirectorio (solo procesamos carpeta base)")
            break
            
        for archivo in archivos:
            _, ext = os.path.splitext(archivo)
            ext = ext.lower()
            #print(f"[DEBUG] Archivo: '{archivo}' -> Extensión: '{ext}'")
            
            if ext in formatos_libros:
                ruta_completa = os.path.join(ruta, archivo)
                print(f"\n✓ Archivo encontrado: {archivo}")

                autor = input("Autor: ").title()
                nuevo_titulo = input("Nuevo título: ").title()
                categoria = input("Categoría: ")
                privado = input("¿Privado? (y/n): ").lower().startswith("y")
                comentarios = input("Comentarios (opcional): ")

                try:
                    fecha_creacion = datetime.fromtimestamp(os.path.getctime(ruta_completa))
                    fecha_modificacion = datetime.fromtimestamp(os.path.getmtime(ruta_completa))
                except Exception:
                    fecha_creacion = fecha_modificacion = None

                datos.append({
                    "titulo_original": os.path.splitext(archivo)[0],
                    "autor": autor,
                    "nuevo_titulo": nuevo_titulo,
                    "extension": ext,
                    "categoria": categoria,
                    "ruta_completa": ruta_completa,
                    "fecha_creacion": fecha_creacion,
                    "fecha_modificacion": fecha_modificacion,
                    "comentarios": comentarios,
                    "privado": privado
                })
    df = pd.DataFrame(datos)
    df["id"] = df.apply(generar_id, axis=1)
    
    print(f"\n[RECOPILAR] Total de libros procesados: {len(df)}")
    return df

def procesar_archivos_catalogo(df):
    for idx, row in df.iterrows():
        ruta = row["ruta_completa"]
        if not os.path.isfile(ruta):
            print(f"[SKIP] No encontrado: {ruta}")
            continue

        categoria_dir = safe_filename(row["categoria"])
        titulo_safe = safe_filename(row["nuevo_titulo"])
        autor_safe = safe_filename(row["autor"])
        nueva_basename = f"{titulo_safe} - {autor_safe}{row['extension']}"
        nueva_dir = os.path.join(DESTINO_BASE_LOCAL, categoria_dir)
        nueva_ruta_local = os.path.join(nueva_dir, nueva_basename)

        # mover
        nueva_ruta_local = mover_archivo_seguro(ruta, nueva_ruta_local)
        df.at[idx, "ruta_local"] = nueva_ruta_local

        # subir a GCS
        if SUBIR_GCS and nueva_ruta_local:
            dest_blob_path = f"{categoria_dir}/{row['id']}_{nueva_basename}"
            gcs_uri = upload_to_gcs(nueva_ruta_local, GCS_BUCKET, dest_blob_path)
            df.at[idx, "uri_gcs"] = gcs_uri
            pub_url, auth_url = construir_urls_gcs(gcs_uri)
            df.at[idx, "url_publica"] = pub_url
            df.at[idx, "url_autenticada"] = auth_url
            print(f"[GCS] Subido: {gcs_uri}")

    if ACTUALIZAR_BIGQUERY:
        upsert_bigquery(df, BQ_DATASET, BQ_TABLE)

    #df.to_csv("E:/Biblioteca_personal/catalogo_incremental.csv", index=False, encoding="utf-8-sig")
    #print("✅ Catálogo incremental actualizado.")

if __name__ == "__main__":
    df_catalogo = recopilar_libros(RUTA_ARCHIVOS_RAW)
    procesar_archivos_catalogo(df_catalogo)