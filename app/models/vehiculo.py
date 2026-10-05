from pydantic import BaseModel, Field


class Vehiculo(BaseModel):
    placa: str = Field(..., min_length=5, max_length=10)
    tipo: str
    capacidad: float
    rendimiento: float