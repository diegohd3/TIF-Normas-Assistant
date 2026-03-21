# TIF Normas Assistant Backend

Backend refactorizado para consulta de normativas TIF de Mexico con FastAPI, PostgreSQL, Alembic y Docker.

## 0) Ubicacion de trabajo

Todos los comandos de este README se ejecutan desde la carpeta raiz del proyecto (`TIF Normas Assistant`).

## 1) Auditoria aplicada

### Conservado y mejorado
- Logica de extraccion de numerales desde PDF (parsing de encabezados, limpieza de ruido, deduplicacion).
- Logica de recuperacion por palabras clave (tokenizacion + ranking local).
- Endpoint `POST /chat` conservado para compatibilidad legacy.
- `POST /chat/query` evolucionado a pipeline por capas (understanding -> retrieval -> validation -> response -> observability).

### Eliminado / sustituido
- Runtime en SQLite para API (migrado a PostgreSQL).
- Estructura monolitica de backend sin capas (`main/db/services` acoplados).
- Configuraciones sensibles hardcodeadas.
- Ruta SQL plana `schema.sql` (sustituida por migraciones Alembic).
- Archivos generados `__pycache__`.

## 2) Arquitectura objetivo (clean-ish)

```text
.
  app/
    api/
      deps.py
      router.py
      routers/
        health.py
        normas.py
        chat.py
    core/
      config.py
    db/
      base.py
      session.py
    models/
      norma.py
      articulo.py
      articulo_chunk.py
    repositories/
      norma_repository.py
      articulo_repository.py
    schemas/
      health.py
      norma.py
      articulo.py
      chat.py
    services/
      retrieval.py
      chat.py
      query_understanding.py
      retrieval_layer.py
      validation_layer.py
      response_layer.py
      observability.py
      compliance_assistant.py
    main.py
  tests/
    test_query_understanding.py
    test_validation_layer.py
  alembic/
    env.py
    versions/20260318_0001_initial_schema.py
  scripts/
    load_normas_pdf.py
    migrate_sqlite_to_postgres.py
  Dockerfile
  docker-compose.yml
  alembic.ini
  requirements.txt
  .env.example
```

## 3) Modelo de datos PostgreSQL

### Tabla `normas`
- `id` BIGINT PK
- `codigo` UNIQUE (ej. `NOM-009-ZOO-1994`)
- `titulo`
- `archivo_origen`
- `created_at`, `updated_at`

### Tabla `articulos`
- `id` BIGINT PK
- `norma_id` FK -> `normas.id`
- `numeral`, `nivel`, `parent_numeral`
- `titulo`, `contenido`
- `pagina_inicio`, `pagina_fin`
- `archivo_origen`
- `contenido_sha256`
- `created_at`, `updated_at`
- UNIQUE (`norma_id`, `numeral`)
- indices para filtros por norma/numeral/padre y GIN de texto

### Tabla `articulo_chunks`
- Base para embeddings/busqueda semantica futura.
- `articulo_id` FK
- `chunk_index`, `contenido`, `token_count`
- `embedding_model`, `embedding` (JSONB)

## 4) Variables de entorno

```env
POSTGRES_DB=tif_normas
POSTGRES_USER=tif
POSTGRES_PASSWORD=tif_password
DATABASE_URL=postgresql+psycopg://tif:tif_password@db:5432/tif_normas
OPENAI_API_KEY=
```

Copiar:

```powershell
Copy-Item .env.example .env
```

## 5) Arranque con Docker Compose (recomendado)

```powershell
docker compose up --build
```

Servicios:
- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- UI dummy de pruebas: `http://localhost:8000/ui`
- PostgreSQL: `localhost:5432`

Compose ejecuta `alembic upgrade head` al iniciar backend.

## 6) Migrar datos existentes (SQLite -> PostgreSQL)

1. Levanta servicios:

```powershell
docker compose up -d db
```

2. Corre migraciones:

```powershell
alembic upgrade head
```

3. Migra datos legacy:

```powershell
python scripts/migrate_sqlite_to_postgres.py --sqlite-path data/normas.db
```

## 7) Cargar normas desde PDF a PostgreSQL

```powershell
python scripts/load_normas_pdf.py ^
  --pdf "C:\\ruta\\NOM-008-ZOO-1994_16111994.pdf" ^
  --pdf "C:\\ruta\\NOM-009-ZOO-1994_161194_Orig.pdf"
```

Modo validacion (sin escritura):

```powershell
python scripts/load_normas_pdf.py --dry-run --pdf "C:\\ruta\\norma.pdf"
```

## 8) Endpoints principales

### Salud
- `GET /health`

### Consulta normativa
- `GET /normas`
- `GET /articulos?norma_codigo=NOM-009-ZOO-1994&limit=20`
- `GET /articulos/{norma_codigo}/{numeral}`
- `GET /articulos/search?q=inspeccion+ante+mortem&norma_codigo=NOM-009-ZOO-1994&top_k=8`

### Chat RAG basico
- `POST /chat`
- `POST /chat/query` (version avanzada con intencion, ambiguedad, confianza y decision policy)

Ejemplo:

```json
{
  "question": "Que exige la norma sobre inspeccion ante-mortem?",
  "norma_codigo": "NOM-009-ZOO-1994",
  "top_k": 8,
  "use_llm": true
}
```

La respuesta incluye trazabilidad (`references`) con numerales y extractos.

## 9) Pipeline de cumplimiento (POST /chat/query)

`/chat/query` implementa 5 capas:

1. `Query Understanding`
- Normaliza texto, corrige errores comunes, expande terminos y clasifica intencion.
- Detecta ambiguedad y entidades normativas (ej. `NOM-009-ZOO-1994`, numerales, temas).
- Soporta inferencia de contexto desde historial (`history`).

2. `Retrieval Layer`
- Usa recuperacion keyword con expansion de sinonimos.
- Re-rankea por cobertura, norma inferida, numeral y tema.

3. `Validation Layer`
- Evalua suficiencia de evidencia, cobertura y conflicto entre fragmentos.
- Calcula `confidence_score` y aplica politica:
  - alta -> `direct_answer`
  - media -> `assumption_answer`
  - baja -> `clarification_needed` o `insufficient_evidence`

4. `Response Layer`
- Separa `Respuesta breve` y `Fundamento`.
- En confianza media explicita supuesto principal y alternativas.
- En baja confianza formula aclaracion breve con 2-3 opciones concretas.

5. `Observability Layer`
- Registra logs estructurados de intencion, ambiguedad, keywords, documentos, score y razones de decision.

## 10) Campos nuevos en /chat/query

Ademas de `answer`, `query_terms`, `references` y `llm_used`, la respuesta avanzada incluye:

- `response_mode`
- `support_level`
- `confidence_score`
- `confidence_level`
- `detected_intent`
- `ambiguity_score`
- `ambiguity_signals`
- `domain_in_scope`
- `extracted_entities`
- `interpretation_candidates`
- `assumptions`
- `alternative_interpretations`
- `clarification`
- `decision_reasons`
- `trace_id`

## 11) Alias versionado

Tambien existen alias bajo `/api/v1` para evolucionar API sin romper clientes legacy:

- `/api/v1/health`
- `/api/v1/normas`
- `/api/v1/articulos`
- `/api/v1/articulos/search`
- `/api/v1/chat`
- `/api/v1/chat/query`
