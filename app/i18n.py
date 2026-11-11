"""Traducciones de la interfaz (es/en/de). Solo textos de la UI, nunca datos del catálogo."""
from jinja2 import pass_context
from starlette.requests import Request

LANGS = {"es": "Español", "en": "English", "de": "Deutsch"}
DEFAULT_LANG = "es"
COOKIE_NAME = "lang"

# Cada entrada: (es, en, de). Las claves *_one / *_other son plurales para tn().
_STRINGS: dict[str, tuple[str, str, str]] = {
    # Base / navegación
    "site_title": ("Biblioteca Personal", "Personal Library", "Persönliche Bibliothek"),
    "brand": ("Biblioteca", "Library", "Bibliothek"),
    "brand_home": ("Biblioteca, inicio", "Library, home", "Bibliothek, Startseite"),
    "skip": ("Saltar al contenido", "Skip to content", "Zum Inhalt springen"),
    "menu_open": ("Abrir menú", "Open menu", "Menü öffnen"),
    "menu_close": ("Cerrar menú", "Close menu", "Menü schließen"),
    "nav_main": ("Navegación principal", "Main navigation", "Hauptnavigation"),
    "nav_catalog": ("Catálogo", "Catalog", "Katalog"),
    "nav_authors": ("Autores", "Authors", "Autoren"),
    "nav_categories": ("Categorías", "Categories", "Kategorien"),
    "nav_upload": ("Subir", "Upload", "Hochladen"),
    "nav_panel": ("Panel", "Admin", "Verwaltung"),
    "logout": ("Cerrar sesión", "Sign out", "Abmelden"),
    "account_of": ("Cuenta de {email}", "Account for {email}", "Konto von {email}"),
    "language": ("Idioma", "Language", "Sprache"),
    # Catálogo
    "collection_label": ("Colección completa", "Complete collection", "Gesamte Sammlung"),
    "hero": ("Sé como Godzilla.", "Be like Godzilla.", "Sei wie Godzilla."),
    "godzilla_q": ("¿Godzilla?", "Godzilla?", "Godzilla?"),
    "catalog_sub": (
        "Busca por título o autor y descarga el formato que necesites.",
        "Search by title or author and download the format you need.",
        "Suche nach Titel oder Autor und lade das passende Format herunter.",
    ),
    "contribute_1": ("También puedes", "You can also", "Du kannst auch"),
    "contribute_2": ("contribuir", "contribute", "beitragen"),
    "upload_file": ("Subir archivo", "Upload file", "Datei hochladen"),
    "msg_uploaded": (
        "Libro subido y publicado en el catálogo.",
        "Book uploaded and published to the catalog.",
        "Buch hochgeladen und im Katalog veröffentlicht.",
    ),
    "msg_processing": (
        "Tu libro se está subiendo y procesando en segundo plano. Aparecerá en el catálogo al terminar.",
        "Your book is uploading and processing in the background. It will appear in the catalog when it's done.",
        "Dein Buch wird im Hintergrund hochgeladen und verarbeitet. Es erscheint im Katalog, sobald es fertig ist.",
    ),
    "see_status": ("Ver estado de publicación", "See publishing status", "Veröffentlichungsstatus ansehen"),
    "search_label": ("Buscar por título o autor", "Search by title or author", "Nach Titel oder Autor suchen"),
    "search_ph": ("Buscar en la biblioteca…", "Search the library…", "In der Bibliothek suchen…"),
    "search_btn": ("Buscar", "Search", "Suchen"),
    "filters": ("Filtros", "Filters", "Filter"),
    "filters_active": ("Activos", "Active", "Aktiv"),
    "category": ("Categoría", "Category", "Kategorie"),
    "author": ("Autor", "Author", "Autor"),
    "title": ("Título", "Title", "Titel"),
    "all_categories": ("Todas las categorías", "All categories", "Alle Kategorien"),
    "all_authors": ("Todos los autores", "All authors", "Alle Autoren"),
    "sort_label": ("Ordenar libros", "Sort books", "Bücher sortieren"),
    "sort_titulo": ("Título A–Z", "Title A–Z", "Titel A–Z"),
    "sort_autor": ("Autor A–Z", "Author A–Z", "Autor A–Z"),
    "sort_fecha": ("Recientes", "Most recent", "Neueste"),
    "apply_filters": ("Aplicar filtros", "Apply filters", "Filter anwenden"),
    "results_one": ("{n} resultado", "{n} result", "{n} Ergebnis"),
    "results_other": ("{n} resultados", "{n} results", "{n} Ergebnisse"),
    "clear_filters": ("Limpiar filtros", "Clear filters", "Filter zurücksetzen"),
    "books_aria": ("Libros", "Books", "Bücher"),
    "col_title_author": ("Título / Autor", "Title / Author", "Titel / Autor"),
    "col_formats": ("Formatos", "Formats", "Formate"),
    "private": ("Privado", "Private", "Privat"),
    "download_as": ("Descargar {title} en {fmt}", "Download {title} as {fmt}", "{title} als {fmt} herunterladen"),
    "no_books": ("No se encontraron libros.", "No books found.", "Keine Bücher gefunden."),
    "no_books_hint": (
        "Prueba otro título o autor, o elimina los filtros.",
        "Try another title or author, or clear the filters.",
        "Versuche einen anderen Titel oder Autor oder setze die Filter zurück.",
    ),
    "see_full": ("Ver colección completa", "View full collection", "Gesamte Sammlung ansehen"),
    "page_of": ("Página {page} de {total}", "Page {page} of {total}", "Seite {page} von {total}"),
    "books_one": ("{n} libro", "{n} book", "{n} Buch"),
    "books_other": ("{n} libros", "{n} books", "{n} Bücher"),
    "pages_nav": ("Páginas del catálogo", "Catalog pages", "Katalogseiten"),
    "prev_page": ("Página anterior", "Previous page", "Vorherige Seite"),
    "next_page": ("Página siguiente", "Next page", "Nächste Seite"),
    "page_n": ("Página {n}", "Page {n}", "Seite {n}"),
    "godzilla_dialog": (
        "¿Godzilla? El origen del nombre de la biblioteca",
        "Godzilla? Where the library's name comes from",
        "Godzilla? Woher der Name der Bibliothek kommt",
    ),
    "close_image": ("Cerrar imagen", "Close image", "Bild schließen"),
    "godzilla_alt": (
        "Godzilla copia y escanea libros de la biblioteca para subirlos gratis a internet. Godzilla entiende que la libertad de acceso a material académico es fundamental para el desarrollo del conocimiento. Sé como Godzilla. Debajo, Godzilla está junto a una fotocopiadora con un libro en las manos.",
        "Godzilla copies and scans library books to upload them to the internet for free. Godzilla understands that free access to academic material is fundamental to the development of knowledge. Be like Godzilla. Below, Godzilla stands next to a photocopier holding a book.",
        "Godzilla kopiert und scannt Bücher aus der Bibliothek, um sie kostenlos ins Internet zu stellen. Godzilla weiß, dass freier Zugang zu wissenschaftlichem Material grundlegend für die Entwicklung von Wissen ist. Sei wie Godzilla. Darunter steht Godzilla mit einem Buch in den Händen neben einem Kopierer.",
    ),
    # Autores
    "authors_count_one": ("{n} autor en tu biblioteca", "{n} author in your library", "{n} Autor in deiner Bibliothek"),
    "authors_count_other": ("{n} autores en tu biblioteca", "{n} authors in your library", "{n} Autoren in deiner Bibliothek"),
    "author_search_ph": ("Buscar autor…", "Search authors…", "Autor suchen…"),
    "author_search_label": ("Buscar autor", "Search authors", "Autor suchen"),
    "alpha_index": ("Índice de autores por letra", "Authors by letter", "Autoren nach Anfangsbuchstabe"),
    "authors_letter": ("Autores: {letter}", "Authors: {letter}", "Autoren: {letter}"),
    "no_authors": ("No hay autores todavía.", "No authors yet.", "Noch keine Autoren."),
    "authors_none_found": (
        "No se encontraron autores. Prueba con otro nombre.",
        "No authors found. Try another name.",
        "Keine Autoren gefunden. Versuche einen anderen Namen.",
    ),
    "authors_found_one": ("{n} autor encontrado.", "{n} author found.", "{n} Autor gefunden."),
    "authors_found_other": ("{n} autores encontrados.", "{n} authors found.", "{n} Autoren gefunden."),
    # Categorías
    "categories_count_one": ("{n} categoría", "{n} category", "{n} Kategorie"),
    "categories_count_other": ("{n} categorías", "{n} categories", "{n} Kategorien"),
    "no_categories": ("No hay categorías todavía.", "No categories yet.", "Noch keine Kategorien."),
    # Subir
    "upload_page": ("Subir libro", "Upload book", "Buch hochladen"),
    "upload_h1": ("Subir un libro", "Upload a book", "Ein Buch hochladen"),
    "upload_owner_sub": (
        "Se publica directo en el catálogo.",
        "It's published straight to the catalog.",
        "Es wird direkt im Katalog veröffentlicht.",
    ),
    "upload_friend_sub": (
        "Queda pendiente hasta que el dueño lo apruebe.",
        "It stays pending until the owner approves it.",
        "Es bleibt ausstehend, bis der Eigentümer es freigibt.",
    ),
    "msg_pending": (
        "Tu libro quedó pendiente de aprobación. El dueño lo revisará pronto.",
        "Your book is awaiting approval. The owner will review it soon.",
        "Dein Buch wartet auf Freigabe. Der Eigentümer prüft es bald.",
    ),
    "file": ("Archivo", "File", "Datei"),
    "upload_limits": (
        "Máximo {mb} MB por archivo. Formatos: PDF, EPUB, MOBI, AZW, AZW3, FB2, CBR, CBZ, TXT y RTF.",
        "Up to {mb} MB per file. Formats: PDF, EPUB, MOBI, AZW, AZW3, FB2, CBR, CBZ, TXT and RTF.",
        "Höchstens {mb} MB pro Datei. Formate: PDF, EPUB, MOBI, AZW, AZW3, FB2, CBR, CBZ, TXT und RTF.",
    ),
    "choose_category": ("Elige una categoría", "Choose a category", "Kategorie wählen"),
    "private_hint": (
        "Privado (solo el propietario de la biblioteca puede verlo y descargarlo)",
        "Private (only the library owner can see and download it)",
        "Privat (nur der Eigentümer der Bibliothek kann es sehen und herunterladen)",
    ),
    "comments_optional": ("Comentarios (opcional)", "Comments (optional)", "Kommentare (optional)"),
    "comments": ("Comentarios", "Comments", "Kommentare"),
    "upload_publish": ("Subir y publicar", "Upload and publish", "Hochladen und veröffentlichen"),
    "send_approval": ("Enviar para aprobación", "Submit for approval", "Zur Freigabe senden"),
    # Panel
    "panel_h1": ("Panel de administración", "Administration", "Verwaltung"),
    "panel_sub": (
        "Aprobaciones, personas autorizadas y categorías",
        "Approvals, authorized people and categories",
        "Freigaben, berechtigte Personen und Kategorien",
    ),
    "your_publications": ("Tus publicaciones", "Your publications", "Deine Veröffentlichungen"),
    "publishing": (
        "Publicando. Actualiza esta página en unos momentos.",
        "Publishing. Refresh this page in a moment.",
        "Wird veröffentlicht. Lade die Seite gleich neu.",
    ),
    "publish_failed": (
        "No se pudo completar la publicación. El archivo se conserva para reintentar.",
        "Publishing couldn't be completed. The file is kept so you can retry.",
        "Die Veröffentlichung konnte nicht abgeschlossen werden. Die Datei bleibt für einen neuen Versuch erhalten.",
    ),
    "retry_publish": ("Reintentar publicación", "Retry publishing", "Veröffentlichung wiederholen"),
    "discard_file": ("Descartar archivo", "Discard file", "Datei verwerfen"),
    "pending_approval": ("Pendientes de aprobación", "Awaiting approval", "Ausstehende Freigaben"),
    "uploaded_by": ("Subido por", "Uploaded by", "Hochgeladen von"),
    "uploaded_on": ("el", "on", "am"),
    "view_original": ("ver/descargar archivo original", "view/download original file", "Originaldatei ansehen/herunterladen"),
    "approve_publish": ("Aprobar y publicar", "Approve and publish", "Freigeben und veröffentlichen"),
    "reject_reason": ("Motivo del rechazo (opcional)", "Reason for rejection (optional)", "Ablehnungsgrund (optional)"),
    "reject": ("Rechazar", "Reject", "Ablehnen"),
    "no_pending": ("No hay libros pendientes.", "No pending books.", "Keine ausstehenden Bücher."),
    "authorized_people": ("Personas autorizadas", "Authorized people", "Berechtigte Personen"),
    "email": ("Email", "Email", "E-Mail"),
    "role": ("Rol", "Role", "Rolle"),
    "status": ("Estado", "Status", "Status"),
    "active": ("Activo", "Active", "Aktiv"),
    "deactivated": ("Desactivado", "Deactivated", "Deaktiviert"),
    "deactivate": ("Desactivar", "Deactivate", "Deaktivieren"),
    "reactivate": ("Reactivar", "Reactivate", "Reaktivieren"),
    "email_ph": ("email@ejemplo.com", "email@example.com", "email@beispiel.de"),
    "name_optional": ("Nombre (opcional)", "Name (optional)", "Name (optional)"),
    "add_friend": ("Agregar amigo", "Add friend", "Freund hinzufügen"),
    "new_category": ("Nueva categoría", "New category", "Neue Kategorie"),
    "add_category": ("Agregar categoría", "Add category", "Kategorie hinzufügen"),
    # Acceso
    "login": ("Iniciar sesión", "Sign in", "Anmelden"),
    "login_sub": (
        "Acceso solo para personas autorizadas.",
        "Access for authorized people only.",
        "Zugang nur für berechtigte Personen.",
    ),
    "login_google": ("Iniciar sesión con Google", "Sign in with Google", "Mit Google anmelden"),
    "unauth_title": ("Acceso no autorizado", "Unauthorized access", "Kein Zugang"),
    "unauth_1": ("El email", "The email address", "Die E-Mail-Adresse"),
    "unauth_2": (
        "no está en la lista de personas autorizadas.",
        "is not on the list of authorized people.",
        "steht nicht auf der Liste der berechtigten Personen.",
    ),
    "unauth_ask": (
        "Pídele al dueño de la biblioteca que te agregue.",
        "Ask the library owner to add you.",
        "Bitte den Eigentümer der Bibliothek, dich hinzuzufügen.",
    ),
    "forbidden": (
        "No tienes permiso para ver esta página.",
        "You don't have permission to view this page.",
        "Du hast keine Berechtigung, diese Seite anzusehen.",
    ),
    "google_email_fail": (
        "No se pudo obtener el email de Google.",
        "Couldn't get your email from Google.",
        "Die E-Mail-Adresse konnte nicht von Google abgerufen werden.",
    ),
}

_INDEX = {code: i for i, code in enumerate(LANGS)}


def _from_accept_language(header: str) -> str | None:
    best, best_q = None, 0.0
    for part in header.split(","):
        piece = part.strip().split(";")
        code = piece[0].strip().lower()[:2]
        q = 1.0
        for param in piece[1:]:
            name, _, value = param.strip().partition("=")
            if name == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
        if code in LANGS and q > best_q:
            best, best_q = code, q
    return best


def get_lang(request: Request) -> str:
    """Idioma elegido (cookie) → Accept-Language del navegador → español."""
    chosen = request.cookies.get(COOKIE_NAME)
    if chosen in LANGS:
        return chosen
    return _from_accept_language(request.headers.get("accept-language", "")) or DEFAULT_LANG


def translate(lang: str, key: str, **kwargs) -> str:
    text = _STRINGS[key][_INDEX.get(lang, 0)]
    return text.format(**kwargs) if kwargs else text


def translate_plural(lang: str, key: str, n: int, **kwargs) -> str:
    return translate(lang, f"{key}_{'one' if n == 1 else 'other'}", n=n, **kwargs)


def _lang_from_context(ctx) -> str:
    request = ctx.get("request")
    return get_lang(request) if request is not None else DEFAULT_LANG


@pass_context
def _t(ctx, key: str, **kwargs) -> str:
    return translate(_lang_from_context(ctx), key, **kwargs)


@pass_context
def _tn(ctx, key: str, n: int, **kwargs) -> str:
    return translate_plural(_lang_from_context(ctx), key, n, **kwargs)


@pass_context
def _current_lang(ctx) -> str:
    return _lang_from_context(ctx)


def install(env) -> None:
    env.globals.update(t=_t, tn=_tn, current_lang=_current_lang, LANGS=LANGS)
