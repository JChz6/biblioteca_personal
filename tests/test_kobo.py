import logging
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

_TMP = tempfile.TemporaryDirectory()
TOKEN = "a" * 64
os.environ.update(OWNER_EMAIL='owner@example.test', GOOGLE_CLIENT_ID='test', GOOGLE_CLIENT_SECRET='test',
    SESSION_SECRET_KEY='test-secret-not-for-production', BASE_URL='https://library.example.test',
    DATABASE_URL=f'sqlite:///{_TMP.name}/test.db', PENDING_DIR=f'{_TMP.name}/pending', KOBO_TOKEN=TOKEN)

from fastapi.testclient import TestClient

from app.kobo import main as kobo

ROWS = [
    {'id': 'pub1', 'nuevo_titulo': 'Cien años: soledad', 'autor': 'García Márquez', 'extension': '.epub',
     'privado': False, 'uri_gcs': 'gs://biblioteca_personal/a/b.epub'},
    {'id': 'priv1', 'nuevo_titulo': 'Secreto', 'autor': 'X', 'extension': '.epub',
     'privado': True, 'uri_gcs': 'gs://biblioteca_personal/s.epub'},
    {'id': 'mobi1', 'nuevo_titulo': 'Mobi', 'autor': 'Y', 'extension': '.mobi',
     'privado': False, 'uri_gcs': 'gs://biblioteca_personal/m.mobi'},
]


class KoboTests(unittest.TestCase):
    def setUp(self):
        kobo._failures.clear()
        kobo.get_kobo_settings.cache_clear()
        patch('app.bigquery.catalogo.get_catalogo', return_value=ROWS).start()
        patch('app.kobo.main.get_catalogo', return_value=ROWS).start()
        self.blob = MagicMock()
        self.blob.generate_signed_url.return_value = 'https://storage.googleapis.com/x?X-Goog-Signature=abc'
        client = MagicMock()
        client.bucket.return_value.blob.return_value = self.blob
        patch('app.kobo.main.get_storage_client', return_value=client).start()
        self.addCleanup(patch.stopall)
        self.c = TestClient(kobo.app, raise_server_exceptions=False)

    def test_valid_token_page(self):
        r = self.c.get(f'/k/{TOKEN}/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Cien años', r.text)
        self.assertIn('href="d/pub1"', r.text)
        self.assertNotIn('<script', r.text)
        self.assertEqual(r.headers['referrer-policy'], 'no-referrer')
        self.assertIn('noindex', r.headers['x-robots-tag'])

    def test_generic_404s(self):
        for path in ['/', f'/k/{TOKEN[:-1]}b/', f'/k/{TOKEN}', '/k/x/', '/login', '/subir', '/docs',
                     '/openapi.json', f'/k/x/d/pub1']:
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

    def test_private_and_unsupported_not_downloadable(self):
        self.assertEqual(self.c.get(f'/k/{TOKEN}/d/priv1', follow_redirects=False).status_code, 404)
        self.assertEqual(self.c.get(f'/k/{TOKEN}/d/mobi1', follow_redirects=False).status_code, 404)

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
