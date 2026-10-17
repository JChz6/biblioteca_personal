"""Bounded format checks; files are never executed or extracted."""
import codecs
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from starlette.exceptions import HTTPException

ALLOWED_EXTENSIONS = ('.pdf', '.epub', '.mobi', '.azw', '.azw3', '.fb2', '.cbr', '.cbz', '.txt', '.rtf')
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.bmp', '.tif', '.tiff'}


def _check_zip(file, extension):
    # Bound the central directory before ZipFile allocates one object per entry.
    file.seek(0, 2)
    size = file.tell()
    file.seek(max(0, size - 65557))
    tail = file.read(65557)
    marker = tail.rfind(b'PK\x05\x06')
    if marker < 0 or len(tail) - marker < 22:
        return False
    _, disk, start_disk, disk_entries, entries, directory_size, _, comment_size = struct.unpack(
        '<4s4H2LH', tail[marker:marker + 22])
    if (tail[max(0, marker - 20):marker - 16] == b'PK\x06\x07'
            or disk or start_disk or disk_entries != entries or entries > 10000
            or directory_size > 4 * 1024 * 1024 or len(tail) - marker != 22 + comment_size):
        return False
    with zipfile.ZipFile(file) as archive:
        files = archive.infolist()
        if any(f.flag_bits & 1 for f in files):
            return False
        if extension == '.epub':
            mime = archive.getinfo('mimetype')
            return (mime.file_size == 20 and archive.read(mime) == b'application/epub+zip'
                    and 'META-INF/container.xml' in archive.namelist())
        if any('..' in Path(f.filename).parts or f.filename.startswith(('/', '\\')) or '\\' in f.filename for f in files):
            return False
        names = [f.filename for f in files if not f.is_dir()]
        return (any(Path(n).suffix.lower() in IMAGE_EXTENSIONS for n in names)
                and all(Path(n).suffix.lower() in IMAGE_EXTENSIONS
                        or n.lower() == 'comicinfo.xml' for n in names))


def validate_book(file, extension):
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, 'Formato no permitido.')
    file.seek(0)
    head = file.read(65536)
    valid = False
    try:
        if extension == '.pdf':
            valid = head.startswith(b'%PDF-')
        elif extension in {'.epub', '.cbz'}:
            valid = head.startswith(b'PK\x03\x04') and _check_zip(file, extension)
        elif extension == '.cbr':
            valid = head.startswith((b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00'))
        elif extension in {'.mobi', '.azw', '.azw3'}:
            valid = head[60:68] == b'BOOKMOBI'
        elif extension == '.rtf':
            valid = head.startswith(b'{\\rtf')
        elif extension == '.fb2':
            # Read only the root; never resolve DTDs/entities or parse the book body.
            if b'<!DOCTYPE' not in head.upper() and b'<!ENTITY' not in head.upper():
                head = codecs.getincrementaldecoder('utf-8-sig')().decode(head, final=False)
                parser = ElementTree.XMLPullParser(events=('start',))
                parser.feed(head)
                root = next(parser.read_events())[1]
                valid = root.tag == '{http://www.gribuser.ru/xml/fictionbook/2.0}FictionBook'
        elif extension == '.txt':
            file.seek(0)
            encoding = 'utf-16' if head.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
            decoder = codecs.getincrementaldecoder(encoding)()
            valid = bool(head)
            while chunk := file.read(65536):
                text = decoder.decode(chunk)
                if any(ord(c) < 32 and c not in '\t\r\n\f' for c in text):
                    valid = False
                    break
            decoder.decode(b'', final=True)
    except (ValueError, KeyError, UnicodeError, zipfile.BadZipFile, RuntimeError,
            ElementTree.ParseError, StopIteration, NotImplementedError):
        valid = False
    finally:
        file.seek(0)
    if not valid:
        raise HTTPException(415, 'El contenido no corresponde a un formato de biblioteca admitido.')


def save_upload(source, destination: Path, max_bytes: int):
    total = 0
    created = False
    try:
        with destination.open('xb') as output:
            created = True
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(413, 'El archivo supera el tamaño máximo permitido.')
                output.write(chunk)
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
