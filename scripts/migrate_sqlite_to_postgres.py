#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.models import Articulo, Norma


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    raw = raw.replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def fetch_sqlite_rows(sqlite_path: Path) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"No existe base SQLite: {sqlite_path}")

    connection = sqlite3.connect(str(sqlite_path))
    connection.row_factory = sqlite3.Row
    try:
        normas = connection.execute(
            """
            SELECT id, codigo, titulo, archivo_origen, created_at, updated_at
            FROM normas
            ORDER BY id
            """
        ).fetchall()
        articulos = connection.execute(
            """
            SELECT
                id,
                norma_id,
                norma_codigo,
                numeral,
                nivel,
                parent_numeral,
                titulo,
                contenido,
                pagina_inicio,
                pagina_fin,
                archivo_origen,
                contenido_sha256,
                created_at,
                updated_at
            FROM articulos
            ORDER BY id
            """
        ).fetchall()
    finally:
        connection.close()
    return normas, articulos


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Migra datos de SQLite legacy a PostgreSQL",
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=Path(settings.legacy_sqlite_path),
        help="Ruta a normas.db de SQLite",
    )
    parser.add_argument(
        "--database-url",
        default=settings.database_url,
        help="URL de PostgreSQL destino",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Tamano de lote para insercion de articulos",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sqlite_path: Path = args.sqlite_path.resolve()
    normas_rows, articulos_rows = fetch_sqlite_rows(sqlite_path=sqlite_path)

    engine = sa.create_engine(args.database_url, pool_pre_ping=True)
    norma_id_by_codigo: dict[str, int] = {}
    inserted_articles = 0

    with Session(engine) as session:
        for row in normas_rows:
            values: dict[str, Any] = {
                "codigo": row["codigo"],
                "titulo": row["titulo"] or row["codigo"],
                "archivo_origen": row["archivo_origen"],
            }
            created_at = parse_datetime(row["created_at"])
            updated_at = parse_datetime(row["updated_at"])
            if created_at:
                values["created_at"] = created_at
            if updated_at:
                values["updated_at"] = updated_at

            norma_stmt = (
                insert(Norma)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[Norma.codigo],
                    set_={
                        "titulo": values["titulo"],
                        "archivo_origen": values["archivo_origen"],
                        "updated_at": values.get("updated_at", sa.func.now()),
                    },
                )
                .returning(Norma.id, Norma.codigo)
            )

            norma_result = session.execute(norma_stmt).one()
            norma_id_by_codigo[str(norma_result.codigo)] = int(norma_result.id)

        session.commit()

        for index, row in enumerate(articulos_rows, start=1):
            norma_codigo = row["norma_codigo"]
            norma_id = norma_id_by_codigo.get(norma_codigo)
            if norma_id is None:
                continue

            values = {
                "norma_id": norma_id,
                "numeral": row["numeral"],
                "nivel": int(row["nivel"]),
                "parent_numeral": row["parent_numeral"],
                "titulo": row["titulo"] or "",
                "contenido": row["contenido"] or "",
                "pagina_inicio": int(row["pagina_inicio"]),
                "pagina_fin": int(row["pagina_fin"]),
                "archivo_origen": row["archivo_origen"],
                "contenido_sha256": row["contenido_sha256"] or "",
            }
            created_at = parse_datetime(row["created_at"])
            updated_at = parse_datetime(row["updated_at"])
            if created_at:
                values["created_at"] = created_at
            if updated_at:
                values["updated_at"] = updated_at

            articulo_stmt = insert(Articulo).values(**values).on_conflict_do_update(
                index_elements=[Articulo.norma_id, Articulo.numeral],
                set_={
                    "nivel": values["nivel"],
                    "parent_numeral": values["parent_numeral"],
                    "titulo": values["titulo"],
                    "contenido": values["contenido"],
                    "pagina_inicio": values["pagina_inicio"],
                    "pagina_fin": values["pagina_fin"],
                    "archivo_origen": values["archivo_origen"],
                    "contenido_sha256": values["contenido_sha256"],
                    "updated_at": values.get("updated_at", sa.func.now()),
                },
            )
            session.execute(articulo_stmt)
            inserted_articles += 1

            if index % args.batch_size == 0:
                session.commit()

        session.commit()

    print(f"Normas migradas: {len(norma_id_by_codigo)}")
    print(f"Articulos procesados: {inserted_articles}")
    print("Migracion SQLite -> PostgreSQL completada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
