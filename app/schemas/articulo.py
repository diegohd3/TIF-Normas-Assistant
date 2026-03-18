from pydantic import BaseModel, ConfigDict, Field


class ArticuloSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    norma_codigo: str
    numeral: str
    nivel: int
    parent_numeral: str | None = None
    titulo: str
    pagina_inicio: int
    pagina_fin: int


class ArticuloDetail(ArticuloSummary):
    contenido: str


class SearchHit(ArticuloDetail):
    score: float = Field(default=0)
    matched_terms: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    norma_codigo: str | None = None
    top_k: int
    query_terms: list[str]
    candidate_count: int
    results: list[SearchHit]

