#!/usr/bin/env python3
"""
Carga articulos/numerales de normas PDF a PostgreSQL.

Uso ejemplo:
python scripts/load_normas_pdf.py ^
  --pdf "C:\\ruta\\NOM-008-ZOO-1994_16111994.pdf" ^
  --pdf "C:\\ruta\\NOM-009-ZOO-1994_161194_Orig.pdf"
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import sqlalchemy as sa
from pypdf import PdfReader
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.models import Articulo, Norma

HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s+(.+)$")
NORMA_CODE_RE = re.compile(r"(NOM-\d{3}-[A-Z]{3}-\d{4})", re.IGNORECASE)

NOISE_PATTERNS = [
    re.compile(r"DIARIO OFICIAL", re.IGNORECASE),
    re.compile(
        r"^(Lunes|Martes|Miercoles|Mi[eé]rcoles|Jueves|Viernes|Sabado|S[aá]bado|Domingo)\b",
        re.IGNORECASE,
    ),
    re.compile(r"^\(?Primera Secci[oó]n\)?$", re.IGNORECASE),
    re.compile(r"^\d{1,2}-\d{1,2}-\d{2}\b"),
    re.compile(r"^\d+\s*$"),
]


@dataclass(slots=True)
class Section:
    numeral: str
    titulo: str
    content_lines: list[str]
    pagina_inicio: int
    pagina_fin: int

    @property
    def nivel(self) -> int:
        return len(self.numeral.split("."))

    @property
    def parent_numeral(self) -> str | None:
        parts = self.numeral.split(".")
        if len(parts) <= 1:
            return None
        return ".".join(parts[:-1])

    @property
    def contenido(self) -> str:
        body = "\n".join(self.content_lines).strip()
        if body:
            return f"{self.titulo}\n{body}"
        return self.titulo


def normalize_line(line: str) -> str:
    line = line.replace("\u00a0", " ")
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def is_noise_line(line: str) -> bool:
    if not line:
        return True
    return any(pattern.search(line) for pattern in NOISE_PATTERNS)


def extract_lines(pdf_path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(pdf_path))
    output: list[tuple[int, str]] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            line = normalize_line(raw_line)
            if is_noise_line(line):
                continue
            output.append((page_number, line))
    return output


def extract_norma_code(pdf_path: Path, lines: Sequence[tuple[int, str]]) -> str:
    filename_match = NORMA_CODE_RE.search(pdf_path.name)
    if filename_match:
        return filename_match.group(1).upper()

    for _, line in lines[:100]:
        line_match = NORMA_CODE_RE.search(line)
        if line_match:
            return line_match.group(1).upper()

    raise ValueError(f"No se pudo detectar codigo NOM en {pdf_path}")


def extract_norma_title(lines: Sequence[tuple[int, str]], fallback_code: str) -> str:
    full_code = fallback_code.upper()
    code_prefix = "-".join(fallback_code.split("-")[:2])  # Ej: NOM-008

    for _, line in lines[:200]:
        upper = line.upper()
        if "NORMA OFICIAL MEXICANA" in upper and full_code in upper:
            return line

    for _, line in lines[:200]:
        upper = line.upper()
        if (
            "NORMA OFICIAL MEXICANA" in upper
            and code_prefix in upper
            and ("-ZOO-" in upper or "-Z00-" in upper)
        ):
            return line

    for _, line in lines[:200]:
        upper = line.upper()
        if "NORMA OFICIAL MEXICANA" in upper and "NOM-" in upper:
            return line

    return fallback_code


def extract_norma_title_from_pdf(pdf_path: Path, fallback_code: str) -> str:
    reader = PdfReader(str(pdf_path))
    code_prefix = "-".join(fallback_code.split("-")[:2])

    for page in reader.pages[:3]:
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            line = normalize_line(raw_line)
            if not line:
                continue
            upper = line.upper()
            if (
                "NORMA OFICIAL MEXICANA" in upper
                and code_prefix in upper
                and ("-ZOO-" in upper or "-Z00-" in upper)
            ):
                return line

    return fallback_code


def parse_sections(lines: Sequence[tuple[int, str]]) -> list[Section]:
    sections: list[Section] = []
    current: Optional[Section] = None

    for page, line in lines:
        match = HEADING_RE.match(line)
        if match:
            numeral, titulo = match.groups()
            if current is not None:
                sections.append(current)
            current = Section(
                numeral=numeral.strip(),
                titulo=titulo.strip(),
                content_lines=[],
                pagina_inicio=page,
                pagina_fin=page,
            )
            continue

        if current is not None:
            current.content_lines.append(line)
            current.pagina_fin = page

    if current is not None:
        sections.append(current)

    return sections


def trim_index_sections(sections: list[Section]) -> list[Section]:
    first_11_index: int | None = None
    for idx, section in enumerate(sections):
        if section.numeral == "1.1":
            first_11_index = idx
            break

    if first_11_index is None:
        return sections

    first_main_index = None
    for idx in range(first_11_index, -1, -1):
        if sections[idx].numeral == "1":
            first_main_index = idx
            break

    start_index = first_main_index if first_main_index is not None else first_11_index
    return sections[start_index:]


def merge_duplicate_numerals(sections: list[Section]) -> list[Section]:
    merged: dict[str, Section] = {}
    order: list[str] = []

    for section in sections:
        existing = merged.get(section.numeral)
        if existing is None:
            merged[section.numeral] = section
            order.append(section.numeral)
            continue

        if section.content_lines:
            existing.content_lines.extend(section.content_lines)
        existing.pagina_fin = max(existing.pagina_fin, section.pagina_fin)

    return [merged[numeral] for numeral in order]


def upsert_norma(session: Session, codigo: str, titulo: str, archivo_origen: str) -> int:
    stmt = (
        insert(Norma)
        .values(
            codigo=codigo,
            titulo=titulo,
            archivo_origen=archivo_origen,
        )
        .on_conflict_do_update(
            index_elements=[Norma.codigo],
            set_={
                "titulo": titulo,
                "archivo_origen": archivo_origen,
                "updated_at": sa.func.now(),
            },
        )
        .returning(Norma.id)
    )
    result = session.execute(stmt).scalar_one()
    return int(result)


def replace_articles(
    session: Session,
    norma_id: int,
    archivo_origen: str,
    sections: Sequence[Section],
) -> int:
    session.execute(sa.delete(Articulo).where(Articulo.norma_id == norma_id))

    for section in sections:
        contenido = section.contenido
        contenido_hash = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
        session.add(
            Articulo(
                norma_id=norma_id,
                numeral=section.numeral,
                nivel=section.nivel,
                parent_numeral=section.parent_numeral,
                titulo=section.titulo,
                contenido=contenido,
                pagina_inicio=section.pagina_inicio,
                pagina_fin=section.pagina_fin,
                archivo_origen=archivo_origen,
                contenido_sha256=contenido_hash,
            )
        )
    return len(sections)


def process_pdf(session: Session, pdf_path: Path) -> tuple[str, int]:
    lines = extract_lines(pdf_path)
    codigo = extract_norma_code(pdf_path, lines)
    titulo = extract_norma_title_from_pdf(pdf_path, codigo)
    if titulo == codigo:
        titulo = extract_norma_title(lines, codigo)

    sections = parse_sections(lines)
    sections = trim_index_sections(sections)
    sections = merge_duplicate_numerals(sections)

    norma_id = upsert_norma(
        session=session,
        codigo=codigo,
        titulo=titulo,
        archivo_origen=str(pdf_path),
    )
    inserted = replace_articles(
        session=session,
        norma_id=norma_id,
        archivo_origen=str(pdf_path),
        sections=sections,
    )
    return codigo, inserted


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Extrae articulos/numerales de normas PDF y los carga en PostgreSQL.",
    )
    parser.add_argument(
        "--database-url",
        default=settings.database_url,
        help="URL de PostgreSQL destino",
    )
    parser.add_argument(
        "--pdf",
        action="append",
        type=Path,
        required=True,
        help="Ruta PDF de norma. Se puede repetir varias veces.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo valida parseo, sin guardar en base de datos.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf_paths = [path.resolve() for path in args.pdf]
    missing = [str(path) for path in pdf_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"No existen estos PDF: {', '.join(missing)}")

    if args.dry_run:
        total = 0
        for pdf in pdf_paths:
            lines = extract_lines(pdf)
            codigo = extract_norma_code(pdf, lines)
            sections = merge_duplicate_numerals(trim_index_sections(parse_sections(lines)))
            print(f"{codigo}: {len(sections)} articulos detectados (dry-run)")
            total += len(sections)
        print(f"Total articulos detectados: {total}")
        return 0

    engine = sa.create_engine(args.database_url, pool_pre_ping=True)
    total = 0
    with Session(engine) as session:
        for pdf in pdf_paths:
            codigo, inserted = process_pdf(session=session, pdf_path=pdf)
            total += inserted
            print(f"{codigo}: {inserted} articulos cargados")
        session.commit()

    print("Carga de normas completada.")
    print(f"Total articulos cargados: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
