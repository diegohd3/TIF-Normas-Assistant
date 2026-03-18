"""initial schema

Revision ID: 20260318_0001
Revises:
Create Date: 2026-03-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260318_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "normas",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("codigo", sa.String(length=64), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("archivo_origen", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo", name="uq_normas_codigo"),
    )
    op.create_index(op.f("ix_normas_codigo"), "normas", ["codigo"], unique=False)

    op.create_table(
        "articulos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("norma_id", sa.BigInteger(), nullable=False),
        sa.Column("numeral", sa.String(length=64), nullable=False),
        sa.Column("nivel", sa.SmallInteger(), nullable=False),
        sa.Column("parent_numeral", sa.String(length=64), nullable=True),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("pagina_inicio", sa.Integer(), nullable=False),
        sa.Column("pagina_fin", sa.Integer(), nullable=False),
        sa.Column("archivo_origen", sa.Text(), nullable=True),
        sa.Column("contenido_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("pagina_inicio >= 1", name="ck_articulos_pagina_inicio_positive"),
        sa.CheckConstraint("pagina_fin >= pagina_inicio", name="ck_articulos_pagina_fin_valid"),
        sa.ForeignKeyConstraint(["norma_id"], ["normas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("norma_id", "numeral", name="uq_articulos_norma_numeral"),
    )
    op.create_index(op.f("ix_articulos_nivel"), "articulos", ["nivel"], unique=False)
    op.create_index(op.f("ix_articulos_norma_id"), "articulos", ["norma_id"], unique=False)
    op.create_index("ix_articulos_norma_numeral", "articulos", ["norma_id", "numeral"], unique=False)
    op.create_index("ix_articulos_norma_parent", "articulos", ["norma_id", "parent_numeral"], unique=False)
    op.create_index(
        "ix_articulos_search_text",
        "articulos",
        [sa.text("to_tsvector('spanish', coalesce(titulo, '') || ' ' || coalesce(contenido, ''))")],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "articulo_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("articulo_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["articulo_id"], ["articulos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("articulo_id", "chunk_index", name="uq_chunks_articulo_index"),
    )
    op.create_index("ix_chunks_articulo", "articulo_chunks", ["articulo_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chunks_articulo", table_name="articulo_chunks")
    op.drop_table("articulo_chunks")

    op.drop_index("ix_articulos_search_text", table_name="articulos")
    op.drop_index("ix_articulos_norma_parent", table_name="articulos")
    op.drop_index("ix_articulos_norma_numeral", table_name="articulos")
    op.drop_index(op.f("ix_articulos_norma_id"), table_name="articulos")
    op.drop_index(op.f("ix_articulos_nivel"), table_name="articulos")
    op.drop_table("articulos")

    op.drop_index(op.f("ix_normas_codigo"), table_name="normas")
    op.drop_table("normas")
