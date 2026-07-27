"""
Migración única: normaliza el casing de `nuevo_titulo` para las filas ya existentes
en BigQuery (títulos que quedaron todo en mayúsculas o todo en minúsculas antes de
que el flujo de aprobación empezara a normalizar automáticamente).

Uso:
    python3 scripts/normalizar_titulos_existentes.py            # dry-run, solo muestra el diff
    python3 scripts/normalizar_titulos_existentes.py --aplicar  # aplica los cambios en BigQuery
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import bigquery  # noqa: E402

from app.bigquery.catalogo import get_bq_client, invalidate_cache  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.text_utils import normalizar_titulo  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aplicar", action="store_true", help="Aplica los cambios en BigQuery (si no, solo dry-run)")
    args = parser.parse_args()

    settings = get_settings()
    client = get_bq_client()
    table = f"{settings.gcp_project_id}.{settings.bq_dataset}.{settings.bq_table}"

    rows = list(client.query(f"SELECT id, nuevo_titulo FROM `{table}`").result())
    cambios = []
    for row in rows:
        nuevo = normalizar_titulo(row["nuevo_titulo"] or "")
        if nuevo != row["nuevo_titulo"]:
            cambios.append({"id": row["id"], "antes": row["nuevo_titulo"], "despues": nuevo})

    print(f"Filas totales: {len(rows)} | Cambiarían: {len(cambios)}\n")
    for c in cambios:
        print(f"  {c['antes']!r}\n  -> {c['despues']!r}\n")

    if not cambios:
        print("Nada que normalizar.")
        return

    backup_path = Path(__file__).resolve().parent / f"backup_titulos_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    backup_path.write_text(json.dumps(cambios, ensure_ascii=False, indent=2))
    print(f"Backup de los valores originales guardado en: {backup_path}")

    if not args.aplicar:
        print("\nDry-run — no se aplicó ningún cambio. Vuelve a correr con --aplicar para escribir en BigQuery.")
        return

    for c in cambios:
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("nuevo", "STRING", c["despues"]),
                bigquery.ScalarQueryParameter("id", "STRING", c["id"]),
            ]
        )
        client.query(f"UPDATE `{table}` SET nuevo_titulo = @nuevo WHERE id = @id", job_config=job_config).result()

    invalidate_cache()
    print(f"\nAplicado: {len(cambios)} títulos actualizados en BigQuery.")


if __name__ == "__main__":
    main()
