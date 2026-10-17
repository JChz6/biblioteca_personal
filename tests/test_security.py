import base64
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

_TMP = tempfile.TemporaryDirectory()
os.environ.update(OWNER_EMAIL='owner@example.test', GOOGLE_CLIENT_ID='test', GOOGLE_CLIENT_SECRET='test',
    SESSION_SECRET_KEY='test-secret-not-for-production', BASE_URL='https://library.example.test',
    DATABASE_URL=f'sqlite:///{_TMP.name}/test.db', PENDING_DIR=f'{_TMP.name}/pending')
from itsdangerous import TimestampSigner
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import Base, engine, SessionLocal, init_db
from app.db.models import User, PendingUpload
from app.config import get_settings


def cookie(email):
    return TimestampSigner(os.environ['SESSION_SECRET_KEY']).sign(base64.b64encode(json.dumps({'email':email}).encode())).decode()


class SecurityTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        init_db()
        with SessionLocal() as db:
            db.add(User(email='friend@example.test', role='friend'))
            db.commit()
        for p in Path(os.environ['PENDING_DIR']).iterdir():
            p.unlink()
        self.client = TestClient(app, base_url=os.environ['BASE_URL'], raise_server_exceptions=False)
        self.client.cookies.set('session', cookie('friend@example.test'))
        self.headers = {'Origin': os.environ['BASE_URL']}
        self.upload = patch('app.services.approval.upload_to_gcs', return_value='gs://biblioteca_personal/test.pdf').start()
        self.upsert = patch('app.services.approval.upsert_libro_aprobado').start()
        patch('app.services.approval.delete_blob').start()
        self.addCleanup(patch.stopall)

    def post_file(self, name='book.pdf', data=b'%PDF-1.7\naudit fixture', **extra):
        fields = dict(autor='Autor', nuevo_titulo='Libro', categoria='Arte')
        fields.update(extra)
        return self.client.post('/subir', files={'archivo':(name,data)},data=fields,headers=self.headers,follow_redirects=False)

    def test_catalog_author_filter_does_not_expose_private_authors(self):
        rows = [
            {'id': 'public', 'nuevo_titulo': 'Visible', 'autor': 'Public Author', 'categoria': 'Arte', 'extension': '.pdf', 'privado': False},
            {'id': 'private', 'nuevo_titulo': 'Private Book', 'autor': 'Private Author', 'categoria': 'Arte', 'extension': '.pdf', 'privado': True},
        ]
        with patch('app.bigquery.catalogo.get_catalogo', return_value=rows):
            response = self.client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Public Author', response.text)
            self.assertNotIn('Private Author', response.text)
            self.client.cookies.set('session', cookie('owner@example.test'))
            self.assertIn('Private Author', self.client.get('/').text)

    def test_author_directory_groups_accents_and_preserves_spanish_order(self):
        from app.routers.catalog import _alphabetical_key, _author_initial
        self.assertEqual(_author_initial('  Álvaro'), 'A')
        self.assertEqual(_author_initial('Émile'), 'E')
        self.assertEqual(_author_initial('Ñora'), 'Ñ')
        self.assertEqual(_author_initial('-'), '#')
        self.assertEqual(sorted(['Óscar', 'Ñora', 'Nuria', 'Álvaro'], key=_alphabetical_key),
                         ['Álvaro', 'Nuria', 'Ñora', 'Óscar'])
        with patch('app.routers.catalog.contar_por_autor', return_value={'Álvaro': 2, 'Ana': 1, 'Ñora': 3}):
            response = self.client.get('/autores')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.count('class="author-group"'), 2)
        self.assertIn('autor=%C3%81lvaro', response.text)

    def test_catalog_pagination_preserves_special_characters_in_filters(self):
        author = 'A & B'
        rows = [dict(id=str(i), nuevo_titulo=f'Book {i}', autor=author,
                     categoria='Arte', extension='.pdf', privado=False) for i in range(25)]
        with patch('app.bigquery.catalogo.get_catalogo', return_value=rows):
            response = self.client.get('/', params={'autor': author})
            self.assertEqual(response.status_code, 200)
            self.assertIn('autor=A%20%26%20B', response.text)

    def test_disguised_executable_rejected_without_staging(self):
        r=self.post_file(data=b'MZ' + b'\0'*100)
        self.assertEqual(r.status_code,415)
        self.assertEqual(list(Path(os.environ['PENDING_DIR']).iterdir()),[])

    def test_disallowed_extension(self):
        self.assertEqual(self.post_file('book.exe').status_code,415)

    def test_invalid_category(self):
        self.assertEqual(self.post_file(categoria='not-a-category').status_code,422)

    def test_friend_requires_approval(self):
        self.assertEqual(self.post_file().status_code,303)
        with SessionLocal() as db:
            self.assertEqual(db.query(PendingUpload).one().status,'pendiente')
        self.upsert.assert_not_called()

    def test_owner_publishes(self):
        self.client.cookies.set('session',cookie('owner@example.test'))
        self.assertEqual(self.post_file().status_code,303)
        with SessionLocal() as db:
            self.assertEqual(db.query(PendingUpload).one().status,'aprobado')
        self.assertEqual(list(Path(os.environ['PENDING_DIR']).iterdir()),[])

    def test_owner_failure_is_not_approval_request_and_can_retry(self):
        self.client.cookies.set('session',cookie('owner@example.test'))
        self.upsert.side_effect=RuntimeError('test failure')
        self.assertEqual(self.post_file().status_code,303)
        with SessionLocal() as db:
            row=db.query(PendingUpload).one()
            self.assertEqual(row.status,'error_publicacion')
            book_id=row.id
        self.upsert.side_effect=None
        r=self.client.post(f'/panel/{book_id}/reintentar',headers=self.headers,follow_redirects=False)
        self.assertEqual(r.status_code,303)
        with SessionLocal() as db:
            self.assertEqual(db.get(PendingUpload,book_id).status,'aprobado')

    def test_cross_origin_admin_request_blocked(self):
        self.client.cookies.set('session',cookie('owner@example.test'))
        r=self.client.post('/panel/usuarios/agregar',data={'email':'intruder@example.test'},headers={'Origin':'https://evil.example.test'},follow_redirects=False)
        self.assertEqual(r.status_code,403)
        with SessionLocal() as db:self.assertIsNone(db.get(User,'intruder@example.test'))

    def test_missing_origin_blocked(self):
        self.assertEqual(self.client.post('/logout',follow_redirects=False).status_code,403)

    def test_same_origin_admin_form_works(self):
        self.client.cookies.set('session',cookie('owner@example.test'))
        r=self.client.post('/panel/usuarios/agregar',data={'email':'new@example.test'},headers=self.headers,follow_redirects=False)
        self.assertEqual(r.status_code,303)
        with SessionLocal() as db:self.assertIsNotNone(db.get(User,'new@example.test'))

    def test_secure_session_cookie(self):
        with patch('app.routers.auth.oauth.google.authorize_access_token', new=AsyncMock(return_value={'userinfo': {'email':'friend@example.test'}})):
            r=self.client.get('/auth/callback',follow_redirects=False)
        h=r.headers['set-cookie'].lower()
        for token in ['secure','httponly','samesite=lax','max-age=86400']:self.assertIn(token,h)

    def test_get_logout_does_not_change_session(self):
        self.assertEqual(self.client.get('/logout',follow_redirects=False).status_code,405)

    def test_file_limit_and_cleanup(self):
        with patch.object(get_settings(),'max_upload_bytes',16):
            self.assertEqual(self.post_file(data=b'%PDF-1.7\n'+b'x'*17).status_code,413)
        with SessionLocal() as db:self.assertEqual(db.query(PendingUpload).count(),0)
        self.assertEqual(list(Path(os.environ['PENDING_DIR']).iterdir()),[])

    def test_epub_structure(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('payload.exe',b'MZ')
        self.assertEqual(self.post_file('book.epub',b.getvalue()).status_code,415)

    def test_overlong_metadata(self):
        self.assertEqual(self.post_file(nuevo_titulo='x'*301).status_code,422)

    def test_anonymous_body_not_parsed(self):
        self.client.cookies.clear()
        r=self.client.post('/subir',content=b'not multipart',headers={**self.headers,'Content-Type':'multipart/form-data; boundary=x'},follow_redirects=False)
        self.assertIn(r.status_code,[303,401])

    def test_global_body_limit_without_content_length(self):
        with patch.object(get_settings(), 'max_upload_bytes', 16):
            r = self.client.post('/subir', content=iter([b'x' * 40000, b'x' * 40000]),
                headers={**self.headers, 'Content-Type': 'application/x-www-form-urlencoded'}, follow_redirects=False)
        self.assertEqual(r.status_code, 413)
        self.assertEqual(list(Path(os.environ['PENDING_DIR']).iterdir()), [])

    def test_pending_quota(self):
        with patch.object(get_settings(), 'max_pending_per_user', 1):
            self.assertEqual(self.post_file().status_code, 303)
            self.assertEqual(self.post_file().status_code, 429)
        with SessionLocal() as db: self.assertEqual(db.query(PendingUpload).count(), 1)

    def test_low_disk_refuses_before_read(self):
        with patch('app.security.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
            self.assertEqual(self.post_file().status_code, 507)
        self.assertEqual(list(Path(os.environ['PENDING_DIR']).iterdir()), [])

    def test_global_staging_quota(self):
        with patch.object(get_settings(), 'max_staging_bytes', 1):
            self.assertEqual(self.post_file().status_code, 507)

    def test_inactive_user_and_friend_admin_denied(self):
        r=self.client.post('/panel/categorias/agregar', data={'nombre':'test'}, headers=self.headers)
        self.assertEqual(r.status_code, 403)
        with SessionLocal() as db:
            user=db.get(User,'friend@example.test'); user.active=False; db.commit()
        self.assertEqual(self.post_file().status_code, 401)

    def test_origin_null_and_host_spoofing_denied(self):
        for origin in ['null','https://library.example.test.evil.test','https://library.example.test:444']:
            r=self.client.post('/logout',headers={'Origin':origin,'Host':'evil.test'},follow_redirects=False)
            self.assertEqual(r.status_code,403)

    def test_logout_post(self):
        r=self.client.post('/logout',headers=self.headers,follow_redirects=False)
        self.assertEqual(r.status_code,303)
        self.assertIn('expires=',r.headers['set-cookie'].lower())

    def test_two_files_rejected(self):
        r=self.client.post('/subir',files=[('archivo',('one.pdf',b'%PDF-1.7')),('extra',('two.pdf',b'%PDF-1.7'))],
            data={'autor':'a','nuevo_titulo':'b','categoria':'Arte'},headers=self.headers)
        self.assertEqual(r.status_code,400)
        self.assertEqual(list(Path(os.environ['PENDING_DIR']).iterdir()),[])

    def test_restart_recovers_owner_jobs_not_friend_requests(self):
        with SessionLocal() as db:
            for email,status in [('owner@example.test','pendiente'),('owner@example.test','procesando'),('friend@example.test','pendiente')]:
                db.add(PendingUpload(uploader_email=email,status=status,local_file_path='test'))
            db.commit()
        init_db()
        with SessionLocal() as db:
            self.assertEqual(db.query(PendingUpload).filter_by(status='error_publicacion').count(),2)
            self.assertEqual(db.query(PendingUpload).filter_by(status='pendiente').one().uploader_email,'friend@example.test')

if __name__=='__main__':unittest.main()
