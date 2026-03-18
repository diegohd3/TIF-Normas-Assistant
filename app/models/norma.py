from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.articulo import Articulo


class Norma(Base):
    __tablename__ = "normas"
    __table_args__ = (sa.UniqueConstraint("codigo", name="uq_normas_codigo"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    archivo_origen: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    articulos: Mapped[list["Articulo"]] = relationship(
        back_populates="norma",
        cascade="all, delete-orphan",
    )

