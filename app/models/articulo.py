from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.articulo_chunk import ArticuloChunk
    from app.models.norma import Norma


class Articulo(Base):
    __tablename__ = "articulos"
    __table_args__ = (
        sa.UniqueConstraint("norma_id", "numeral", name="uq_articulos_norma_numeral"),
        sa.Index("ix_articulos_norma_numeral", "norma_id", "numeral"),
        sa.Index("ix_articulos_norma_parent", "norma_id", "parent_numeral"),
        sa.Index("ix_articulos_nivel", "nivel"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    norma_id: Mapped[int] = mapped_column(
        sa.ForeignKey("normas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    numeral: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    nivel: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    parent_numeral: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    titulo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    contenido: Mapped[str] = mapped_column(sa.Text, nullable=False)
    pagina_inicio: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    pagina_fin: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    archivo_origen: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    contenido_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)

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

    norma: Mapped["Norma"] = relationship(back_populates="articulos")
    chunks: Mapped[list["ArticuloChunk"]] = relationship(
        back_populates="articulo",
        cascade="all, delete-orphan",
    )

