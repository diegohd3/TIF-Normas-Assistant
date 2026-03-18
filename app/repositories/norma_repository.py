from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.articulo import Articulo
from app.models.norma import Norma


@dataclass(slots=True)
class NormaWithCount:
    codigo: str
    titulo: str
    archivo_origen: str | None
    total_articulos: int


class NormaRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_normas(self) -> list[NormaWithCount]:
        stmt = (
            sa.select(
                Norma.codigo,
                Norma.titulo,
                Norma.archivo_origen,
                sa.func.count(Articulo.id).label("total_articulos"),
            )
            .outerjoin(Articulo, Articulo.norma_id == Norma.id)
            .group_by(Norma.id, Norma.codigo, Norma.titulo, Norma.archivo_origen)
            .order_by(Norma.codigo)
        )
        rows = self.db.execute(stmt).all()
        return [
            NormaWithCount(
                codigo=row.codigo,
                titulo=row.titulo,
                archivo_origen=row.archivo_origen,
                total_articulos=int(row.total_articulos),
            )
            for row in rows
        ]

    def get_by_codigo(self, codigo: str) -> Norma | None:
        stmt = sa.select(Norma).where(Norma.codigo == codigo).limit(1)
        return self.db.scalars(stmt).first()

