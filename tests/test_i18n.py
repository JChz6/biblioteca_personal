import os
import unittest

from fastapi.testclient import TestClient

from app import i18n


class I18nTests(unittest.TestCase):
    def setUp(self):
        # Import tardío: test_security y test_kobo fijan el entorno al importarse y la app lo cachea.
        import test_security  # noqa: F401
        from app.main import app
        self.client = TestClient(app, base_url=os.environ['BASE_URL'])

    def test_every_string_has_three_languages(self):
        for key, values in i18n._STRINGS.items():
            self.assertEqual(len(values), len(i18n.LANGS), key)
            self.assertTrue(all(values), key)

    def test_default_is_spanish(self):
        self.assertIn('Iniciar sesión con Google', self.client.get('/login').text)

    def test_accept_language_is_used_without_cookie(self):
        r = self.client.get('/login', headers={'Accept-Language': 'fr;q=1, de;q=0.8, en;q=0.5'})
        self.assertIn('Mit Google anmelden', r.text)
        self.assertIn('<html lang="de">', r.text)

    def test_cookie_overrides_browser(self):
        self.client.cookies.set('lang', 'en')
        r = self.client.get('/login', headers={'Accept-Language': 'de'})
        self.assertIn('Sign in with Google', r.text)

    def test_switch_sets_cookie_and_redirects_back(self):
        r = self.client.get('/idioma/en?next=/autores%3Fq%3Dx', follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers['location'], '/autores?q=x')
        self.assertIn('lang=en', r.headers['set-cookie'])

    def test_switch_rejects_external_redirects_and_unknown_codes(self):
        for target in ('//evil.example', '/\\evil.example', 'https://evil.example'):
            r = self.client.get('/idioma/en', params={'next': target}, follow_redirects=False)
            self.assertEqual(r.headers['location'], '/')
        r = self.client.get('/idioma/xx', follow_redirects=False)
        self.assertNotIn('set-cookie', r.headers)

    def test_plural(self):
        self.assertEqual(i18n.translate_plural('de', 'books', 1), '1 Buch')
        self.assertEqual(i18n.translate_plural('en', 'books', 3), '3 books')


if __name__ == '__main__':
    unittest.main()
