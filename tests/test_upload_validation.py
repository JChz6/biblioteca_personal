import io
import tempfile
import unittest
from pathlib import Path
from app.upload_validation import validate_book, save_upload

class UploadValidationTests(unittest.TestCase):
    def test_pdf_signature(self):
        with self.assertRaises(Exception):validate_book(io.BytesIO(b'MZ fake'), '.pdf')
        validate_book(io.BytesIO(b'%PDF-1.7\n'), '.pdf')

    def test_partial_copy_is_removed(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'book.pdf'
            with self.assertRaises(Exception):save_upload(io.BytesIO(b'x'*17),path,16)
            self.assertFalse(path.exists())

    def test_exact_limit_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'book.pdf'
            save_upload(io.BytesIO(b'x'*16),path,16)
            self.assertEqual(path.stat().st_size,16)

    def test_existing_file_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'book.pdf'; path.write_bytes(b'original')
            with self.assertRaises(FileExistsError):save_upload(io.BytesIO(b'new'),path,16)
            self.assertEqual(path.read_bytes(),b'original')

    def test_supported_book_signatures(self):
        samples={'.mobi':b'\0'*60+b'BOOKMOBI', '.azw':b'\0'*60+b'BOOKMOBI',
            '.azw3':b'\0'*60+b'BOOKMOBI', '.cbr':b'Rar!\x1a\x07\x01\x00',
            '.rtf':b'{\\rtf1 text}', '.txt':'Biblioteca: español'.encode(),
            '.fb2':b'<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><body/>'}
        for ext,body in samples.items():
            with self.subTest(ext=ext):validate_book(io.BytesIO(body),ext)

    def test_valid_epub_and_cbz(self):
        import zipfile
        for ext in ['.epub','.cbz']:
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w') as z:
                if ext=='.epub':
                    z.writestr('mimetype','application/epub+zip')
                    z.writestr('META-INF/container.xml','<container/>')
                else:z.writestr('page1.jpg',b'\xff\xd8\xff')
            validate_book(data,ext)

    def test_fb2_entities_rejected(self):
        data=b'<!DOCTYPE FictionBook [<!ENTITY x "bad">]><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        with self.assertRaises(Exception):validate_book(io.BytesIO(data),'.fb2')

    def test_binary_text_rejected(self):
        with self.assertRaises(Exception):validate_book(io.BytesIO(b'MZ\0binary'),'.txt')
