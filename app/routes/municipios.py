from fastapi import APIRouter, Query

from app.services.municipios import (
    buscar_municipios,
    listar_departamentos,
    listar_municipios_por_departamento,
    obtener_municipio_por_codigo,
)


router = APIRouter(
    prefix="/municipios",
    tags=["Municipios"],
)


@router.get("/departamentos")
async def obtener_departamentos():
    return {
        "departamentos": await listar_departamentos()
    }


@router.get("/departamento/{codigo_departamento}")
async def obtener_municipios_departamento(
    codigo_departamento: str,
):
    return {
        "codigo_departamento": codigo_departamento,
        "municipios": await listar_municipios_por_departamento(
            codigo_departamento
        ),
    }


@router.get("/buscar")
async def buscar(
    q: str = Query(..., min_length=2),
    limite: int = Query(default=20, ge=1, le=50),
):
    return {
        "consulta": q,
        "resultados": await buscar_municipios(q, limite),
    }


@router.get("/{codigo_municipio}")
async def obtener_municipio(codigo_municipio: str):
    return await obtener_municipio_por_codigo(codigo_municipio)
