import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base, Categoria, User

# Categorías sembradas a partir de las existentes en BigQuery al momento de esta migración.
# "Política y Sociedad" / "Política y sociedad" llegaban duplicadas por capitalización inconsistente
# en los datos históricos; se deja una sola forma canónica para el dropdown de aquí en adelante.
CATEGORIAS_INICIALES = [
    "Antropología", "Arte", "Café", "Ciencia", "Cocina", "Cómics",
    "Diseño gráfico", "Economía", "Filosofía", "Finanzas", "Habilidades",
    "Idiomas", "Lingüística", "Literatura", "Mitos y magia", "Negocios",
    "Política y Sociedad", "Psicología", "Relaciones interpersonales",
    "Semiótica", "Tecnología",
]

settings = get_settings()
os.makedirs(os.path.dirname(settings.database_url.removeprefix("sqlite:///")) or ".", exist_ok=True)
os.makedirs(settings.pending_dir, exist_ok=True)

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        owner = db.get(User, settings.owner_email)
        if owner is None:
            db.add(User(email=settings.owner_email, role="owner", display_name="Owner", added_by="system"))
        elif owner.role != "owner":
            owner.role = "owner"

        existing = {c.nombre for c in db.query(Categoria).all()}
        for nombre in CATEGORIAS_INICIALES:
            if nombre not in existing:
                db.add(Categoria(nombre=nombre))

        db.commit()
