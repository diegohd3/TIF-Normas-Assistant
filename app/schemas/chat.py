from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=4000)
    norma_codigo: str | None = Field(
        default=None,
        description="Opcional: limita la consulta a una norma especifica",
    )
    top_k: int | None = Field(default=None, ge=1, le=50)
    use_llm: bool = Field(
        default=True,
        description="Cuando es false solo regresa recuperacion y trazabilidad",
    )


class ChatReference(BaseModel):
    norma_codigo: str
    numeral: str
    titulo: str
    pagina_inicio: int
    pagina_fin: int
    score: float
    excerpt: str


class ChatResponse(BaseModel):
    answer: str
    llm_used: bool
    query_terms: list[str]
    references: list[ChatReference]

