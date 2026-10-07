from typing import Literal

from fastapi import APIRouter, Query

from app.services.combustibles import obtener_precio_combustible


router = APIRouter(
    prefix="/combustibles",
    tags=["Combustibles"],
)


@router.get("/precio")
async def consultar_precio(
    codigo_municipio: str = Query(..., min_length=5, max_length=5),
    producto: Literal["acpm", "gasolina"] = Query(...),
):
    return await obtener_precio_combustible(
        codigo_municipio=codigo_municipio,
        producto=producto,
    )
