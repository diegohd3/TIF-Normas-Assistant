from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.articulo import Articulo
from app.models.norma import Norma


@dataclass(slots=True)
class ArticuloRecord:
    id: int
    norma_codigo: str
    numeral: str
    nivel: int
    parent_numeral: str | None
    titulo: str
    contenido: str
    pagina_inicio: int
    pagina_fin: int


class ArticuloRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _base_stmt() -> sa.Select:
        return (
            sa.select(
                Articulo.id,
                Norma.codigo.label("norma_codigo"),
                Articulo.numeral,
                Articulo.nivel,
                Articulo.parent_numeral,
                Articulo.titulo,
                Articulo.contenido,
                Articulo.pagina_inicio,
                Articulo.pagina_fin,
            )
            .join(Norma, Articulo.norma_id == Norma.id)
            .order_by(Norma.codigo, Articulo.nivel, Articulo.numeral)
        )

    @staticmethod
    def _to_records(rows: list[sa.RowMapping]) -> list[ArticuloRecord]:
        return [
            ArticuloRecord(
                id=int(row["id"]),
                norma_codigo=str(row["norma_codigo"]),
                numeral=str(row["numeral"]),
                nivel=int(row["nivel"]),
                parent_numeral=row["parent_numeral"],
                titulo=str(row["titulo"]),
                contenido=str(row["contenido"]),
                pagina_inicio=int(row["pagina_inicio"]),
                pagina_fin=int(row["pagina_fin"]),
            )
            for row in rows
        ]

    def list_articulos(
        self,
        norma_codigo: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ArticuloRecord]:
        stmt = self._base_stmt().limit(limit).offset(offset)
        if norma_codigo:
            stmt = stmt.where(Norma.codigo == norma_codigo)

        rows = self.db.execute(stmt).mappings().all()
        return self._to_records(rows)

    def get_articulo(self, norma_codigo: str, numeral: str) -> ArticuloRecord | None:
        stmt = (
            self._base_stmt()
            .where(
                Norma.codigo == norma_codigo,
                Articulo.numeral == numeral,
            )
            .limit(1)
        )
        row = self.db.execute(stmt).mappings().first()
        if row is None:
            return None
        return self._to_records([row])[0]

    def search_candidates(
        self,
        terms: list[str],
        norma_codigo: str | None,
        limit: int,
    ) -> list[ArticuloRecord]:
        stmt = self._base_stmt().limit(limit)

        if norma_codigo:
            stmt = stmt.where(Norma.codigo == norma_codigo)

        if terms:
            filters = []
            for term in terms:
                like_term = f"%{term}%"
                filters.append(
                    sa.or_(
                        sa.func.lower(Articulo.titulo).like(like_term),
                        sa.func.lower(Articulo.contenido).like(like_term),
                        Articulo.numeral.ilike(like_term),
                    )
                )
            stmt = stmt.where(sa.or_(*filters))

        rows = self.db.execute(stmt).mappings().all()
        return self._to_records(rows)

