from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.articulo import Articulo


class ArticuloChunk(Base):
    """
    Base preparada para embeddings y busqueda semantica futura.
    """

    __tablename__ = "articulo_chunks"
    __table_args__ = (
        sa.UniqueConstraint("articulo_id", "chunk_index", name="uq_chunks_articulo_index"),
        sa.Index("ix_chunks_articulo", "articulo_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    articulo_id: Mapped[int] = mapped_column(
        sa.ForeignKey("articulos.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    contenido: Mapped[str] = mapped_column(sa.Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    articulo: Mapped["Articulo"] = relationship(back_populates="chunks")

