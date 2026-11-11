import logging
import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_TMP = tempfile.TemporaryDirectory()
TOKEN = "a" * 64
os.environ.update(OWNER_EMAIL='owner@example.test', GOOGLE_CLIENT_ID='test', GOOGLE_CLIENT_SECRET='test',
    SESSION_SECRET_KEY='test-secret-not-for-production', BASE_URL='https://library.example.test',
    DATABASE_URL=f'sqlite:///{_TMP.name}/test.db', PENDING_DIR=f'{_TMP.name}/pending', KOBO_TOKEN=TOKEN)

from fastapi.testclient import TestClient

from app.kobo import main as kobo


def row(id, titulo, autor='Autor', ext='.epub', privado=False, fecha=datetime(2025, 1, 1)):
    return {'id': id, 'nuevo_titulo': titulo, 'autor': autor, 'extension': ext, 'privado': privado,
            'uri_gcs': f'gs://biblioteca_personal/x/{id}{ext}', 'fecha_modificacion': fecha}


ROWS = [
    row('pub1', 'Cien años: soledad', 'García Márquez', fecha=datetime(2024, 1, 1)),
    row('pub1pdf', 'Cien años: soledad', 'García Márquez', ext='.pdf', fecha=datetime(2024, 1, 1)),
    row('priv1', 'Secreto', 'X', privado=True, fecha=datetime(2026, 5, 1)),
    row('mobi1', 'Mobi', 'Y', ext='.mobi', fecha=datetime(2025, 6, 1)),
    row('fb21', 'Solo FB2', 'Z', ext='.fb2', fecha=datetime(2026, 9, 1)),
    row('nuevo', 'Árbol nuevo', 'W', fecha=datetime(2026, 10, 1)),
]


class KoboTests(unittest.TestCase):
    def setUp(self):
        kobo._failures.clear()
        kobo._sizes.clear()
        kobo.get_kobo_settings.cache_clear()
        self.rows = list(ROWS)
        patch('app.bigquery.catalogo.get_catalogo', side_effect=lambda: self.rows).start()
        patch('app.kobo.main.get_catalogo', side_effect=lambda: self.rows).start()
        self.blob = MagicMock()
        self.blob.generate_signed_url.return_value = 'https://storage.googleapis.com/x?X-Goog-Signature=abc'
        client = MagicMock()
        client.bucket.return_value.blob.return_value = self.blob
        client.list_blobs.return_value = [SimpleNamespace(name='x/pub1.epub', size=1_234_567),
                                          SimpleNamespace(name='x/pub1pdf.pdf', size=45_000)]
        patch('app.kobo.main.get_storage_client', return_value=client).start()
        self.addCleanup(patch.stopall)
        self.c = TestClient(kobo.app, raise_server_exceptions=False)

    def get_list(self, qs=''):
        r = self.c.get(f'/k/{TOKEN}/{qs}')
        self.assertEqual(r.status_code, 200)
        return r.text

    def test_list_basics(self):
        r = self.c.get(f'/k/{TOKEN}/')
        self.assertIn('Cien años', r.text)
        self.assertNotIn('<script', r.text)
        self.assertNotIn('<img', r.text)
        self.assertEqual(r.headers['referrer-policy'], 'no-referrer')
        self.assertIn('noindex', r.headers['x-robots-tag'])
        self.assertLess(len(r.content), 20_000)

    def test_order_newest_first_includes_private_and_mobi_hides_unsupported(self):
        html = self.get_list()
        positions = [html.index(t) for t in ('Árbol nuevo', 'Secreto', 'Mobi', 'Cien años')]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('Solo FB2', html)

    def test_formats_grouped_epub_first_with_sizes(self):
        html = self.get_list()
        epub = html.index('href="d/pub1"')
        pdf = html.index('href="d/pub1pdf"')
        self.assertLess(epub, pdf)
        self.assertIn('EPUB &middot; 1,2 MB', html)
        self.assertIn('PDF &middot; 45 KB', html)
        self.assertEqual(html.count('Cien años'), 1)

    def test_letter_filter_and_index(self):
        html = self.get_list('?l=A')
        self.assertIn('Árbol nuevo', html)
        self.assertNotIn('Cien años', html)
        self.assertIn('href="?l=C"', html)
        self.assertNotIn('href="?l=B"', html)  # sin libros con B, no hay enlace

    def test_search(self):
        html = self.get_list('?q=marquez')
        self.assertIn('Cien años', html)
        self.assertNotIn('Secreto', html)

    def test_pagination(self):
        self.rows = [row(f'b{i:03}', f'Libro {i:03}', fecha=datetime(2020, 1, 1, 0, i)) for i in range(45)]
        p1 = self.get_list()
        self.assertIn('1 / 3', p1)
        self.assertIn('href="?p=2"', p1)
        self.assertNotIn('Anterior', p1)
        self.assertIn('Libro 044', p1)
        p3 = self.get_list('?p=3')
        self.assertIn('Libro 000', p3)
        self.assertIn('href="./"', p3)
        self.assertNotIn('Siguiente', p3)
        self.assertIn('3 / 3', self.get_list('?p=99'))
        self.assertIn('1 / 3', self.get_list('?p=abc'))

    def test_list_without_bucket_sizes(self):
        kobo.get_storage_client.return_value.list_blobs.side_effect = RuntimeError('boom')
        html = self.get_list()
        self.assertIn('Descargar EPUB</a>', html)

    def test_generic_404s(self):
        for path in ['/', f'/k/{TOKEN[:-1]}b/', f'/k/{TOKEN}', '/k/x/', '/login', '/subir', '/docs',
                     '/openapi.json', '/k/x/d/pub1', f'/k/{TOKEN}/p/pub1']:
            r = self.c.get(path, follow_redirects=False)
            self.assertEqual(r.status_code, 404, path)
            self.assertEqual(r.text, 'Not Found', path)

    def test_read_only(self):
        for method in ('post', 'put', 'delete', 'patch'):
            self.assertEqual(getattr(self.c, method)(f'/k/{TOKEN}/').status_code, 404)

    def test_robots(self):
        self.assertEqual(self.c.get('/robots.txt').text, 'User-agent: *\nDisallow: /\n')

    def test_signed_redirect(self):
        r = self.c.get(f'/k/{TOKEN}/d/pub1', follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers['location'].startswith('https://storage.googleapis.com/'))
        kw = self.blob.generate_signed_url.call_args.kwargs
        self.assertEqual(kw['version'], 'v4')
        self.assertEqual(kw['response_type'], 'application/epub+zip')
        self.assertEqual(kw['response_disposition'], 'attachment; filename="Cien anos soledad - Garcia Marquez.epub"')

    def test_proxy_mode_streams_through_service(self):
        os.environ['KOBO_DOWNLOAD_MODE'] = 'proxy'
        kobo.get_kobo_settings.cache_clear()
        try:
            gcs_blob = SimpleNamespace(size=7)
            kobo.get_storage_client.return_value.bucket.return_value.get_blob.return_value = gcs_blob
            with patch('app.kobo.main.stream_blob', return_value=iter([b'abc', b'defg'])):
                r = self.c.get(f'/k/{TOKEN}/d/pub1', follow_redirects=False)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.content, b'abcdefg')
            self.assertEqual(r.headers['content-length'], '7')
            self.assertEqual(r.headers['content-type'], 'application/epub+zip')
            self.assertEqual(r.headers['content-disposition'], 'attachment; filename="Cien anos soledad - Garcia Marquez.epub"')
            self.blob.generate_signed_url.assert_not_called()
        finally:
            del os.environ['KOBO_DOWNLOAD_MODE']

    def test_private_and_mobi_downloadable_unsupported_not(self):
        self.assertEqual(self.c.get(f'/k/{TOKEN}/d/priv1', follow_redirects=False).status_code, 302)
        self.assertEqual(self.c.get(f'/k/{TOKEN}/d/mobi1', follow_redirects=False).status_code, 302)
        self.assertEqual(self.blob.generate_signed_url.call_args.kwargs['response_type'], 'application/x-mobipocket-ebook')
        self.assertEqual(self.c.get(f'/k/{TOKEN}/d/fb21', follow_redirects=False).status_code, 404)

    def test_rate_limit_blocks_after_failures(self):
        os.environ['KOBO_MAX_FAILURES'] = '3'
        kobo.get_kobo_settings.cache_clear()
        try:
            h = {'CF-Connecting-IP': '203.0.113.9'}
            for _ in range(3):
                self.assertEqual(self.c.get('/k/wrong/', headers=h).status_code, 404)
            self.assertEqual(self.c.get(f'/k/{TOKEN}/', headers=h).status_code, 429)
            self.assertEqual(self.c.get(f'/k/{TOKEN}/', headers={'CF-Connecting-IP': '203.0.113.10'}).status_code, 200)
        finally:
            del os.environ['KOBO_MAX_FAILURES']

    def test_token_masked_in_access_log(self):
        rec = logging.LogRecord('uvicorn.access', logging.INFO, '', 0, '%s "%s %s HTTP/%s" %d',
                                ('1.2.3.4', 'GET', f'/k/{TOKEN}/d/pub1', '1.1', 302), None)
        kobo._MaskTokenFilter().filter(rec)
        self.assertNotIn(TOKEN, rec.getMessage())
        self.assertIn('/k/***/d/pub1', rec.getMessage())

    def test_short_token_rejected(self):
        os.environ['KOBO_TOKEN'] = 'short'
        kobo.get_kobo_settings.cache_clear()
        try:
            with self.assertRaises(Exception):
                kobo.get_kobo_settings()
        finally:
            os.environ['KOBO_TOKEN'] = TOKEN


if __name__ == '__main__':
    unittest.main()
