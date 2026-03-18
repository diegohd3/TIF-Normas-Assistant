from pydantic import BaseModel, ConfigDict


class NormaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    titulo: str
    archivo_origen: str | None = None
    total_articulos: int = 0

