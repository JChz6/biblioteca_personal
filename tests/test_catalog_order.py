from datetime import datetime
import unittest

from app.bigquery.catalogo import agrupar_por_obra, ordenar_grupos


class CatalogOrderTests(unittest.TestCase):
    def test_recent_order_uses_modification_then_author_then_title(self):
        older = datetime(2025, 1, 1)
        newer = datetime(2026, 1, 1)
        rows = [
            dict(autor='B', nuevo_titulo='A', fecha_modificacion=newer),
            dict(autor='A', nuevo_titulo='Z', fecha_modificacion=newer),
            dict(autor='A', nuevo_titulo='A', fecha_modificacion=older, fecha_carga=datetime(2027, 1, 1)),
            dict(autor='A', nuevo_titulo='B', fecha_modificacion=newer),
            dict(autor='A', nuevo_titulo='Missing', fecha_modificacion=None),
        ]
        ordered = ordenar_grupos(rows, 'fecha')
        self.assertEqual([r['nuevo_titulo'] for r in ordered], ['B', 'Z', 'A', 'A', 'Missing'])
        self.assertEqual([r['autor'] for r in ordered], ['A', 'A', 'B', 'A', 'A'])

    def test_group_uses_latest_modification_across_formats(self):
        rows = [
            dict(id='pdf', autor='Autor', nuevo_titulo='Libro', extension='pdf', fecha_modificacion=datetime(2025, 1, 1)),
            dict(id='epub', autor='Autor', nuevo_titulo='Libro', extension='epub', fecha_modificacion=datetime(2026, 1, 1)),
            dict(id='txt', autor='Autor', nuevo_titulo='Libro', extension='txt', fecha_modificacion=None),
        ]
        group, = agrupar_por_obra(rows)
        self.assertEqual(group['fecha_modificacion'], datetime(2026, 1, 1))
        self.assertEqual(len(group['formatos']), 3)
