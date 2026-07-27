import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    role: Mapped[str] = mapped_column(String, default="friend")  # "owner" | "friend"
    display_name: Mapped[str] = mapped_column(String, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    added_by: Mapped[str] = mapped_column(String, default="")


class Categoria(Base):
    __tablename__ = "categorias"

    nombre: Mapped[str] = mapped_column(String, primary_key=True)


class PendingUpload(Base):
    __tablename__ = "pending_uploads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    local_file_path: Mapped[str] = mapped_column(String)
    titulo_original: Mapped[str] = mapped_column(String, default="")
    autor: Mapped[str] = mapped_column(String, default="")
    nuevo_titulo: Mapped[str] = mapped_column(String, default="")
    extension: Mapped[str] = mapped_column(String, default="")
    categoria: Mapped[str] = mapped_column(String, default="")
    comentarios: Mapped[str] = mapped_column(String, default="")
    privado: Mapped[bool] = mapped_column(Boolean, default=False)

    uploader_email: Mapped[str] = mapped_column(ForeignKey("users.email"))
    status: Mapped[str] = mapped_column(String, default="pendiente")  # pendiente | aprobado | rechazado

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    catalogo_id: Mapped[str | None] = mapped_column(String, nullable=True)
