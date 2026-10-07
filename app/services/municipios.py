import os
import time
import unicodedata
from typing import Any

import certifi
import httpx
from fastapi import HTTPException


DIVIPOLA_URL = "https://www.datos.gov.co/resource/gdxc-w37w.json"
CACHE_SEGUNDOS = 86400

_cache: dict[str, Any] = {
    "datos": None,
    "actualizado_en": 0.0,
}


def _texto_normalizado(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "")
    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return " ".join(texto.upper().strip().split())


def _a_float(valor: Any) -> float | None:
    if valor is None:
        return None

    texto = str(valor).strip().replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


def _normalizar_registro(registro: dict) -> dict | None:
    codigo_departamento = str(registro.get("cod_dpto", "")).strip()
    departamento = str(registro.get("dpto", "")).strip()
    codigo_municipio = str(registro.get("cod_mpio", "")).strip()
    municipio = str(registro.get("nom_mpio", "")).strip()
    tipo = str(registro.get("tipo_municipio", "")).strip()
    longitud = _a_float(registro.get("longitud"))
    latitud = _a_float(registro.get("latitud"))

    if not codigo_municipio or not municipio:
        return None

    return {
        "codigo_departamento": codigo_departamento,
        "departamento": departamento,
        "codigo_municipio": codigo_municipio,
        "municipio": municipio,
        "tipo": tipo,
        "longitud": longitud,
        "latitud": latitud,
    }


async def obtener_catalogo_municipios(
    forzar_actualizacion: bool = False,
) -> list[dict]:
    ahora = time.time()
    datos_cache = _cache["datos"]

    if (
        not forzar_actualizacion
        and datos_cache is not None
        and ahora - _cache["actualizado_en"] < CACHE_SEGUNDOS
    ):
        return datos_cache

    headers = {}
    app_token = os.getenv("SOCRATA_APP_TOKEN")

    if app_token:
        headers["X-App-Token"] = app_token

    parametros = {
        "$limit": 5000,
        "$select": (
            "cod_dpto,dpto,cod_mpio,nom_mpio,"
            "tipo_municipio,longitud,latitud"
        ),
        "$order": "dpto ASC, nom_mpio ASC",
    }

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            verify=certifi.where(),
            trust_env=False,
        ) as cliente:
            respuesta = await cliente.get(
                DIVIPOLA_URL,
                params=parametros,
                headers=headers,
            )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail="La consulta de municipios tardó demasiado en responder.",
        ) from error
    except httpx.RequestError as error:
        if datos_cache is not None:
            return datos_cache

        raise HTTPException(
            status_code=503,
            detail={
                "mensaje": "No fue posible consultar el catálogo de municipios.",
                "tipo_error": type(error).__name__,
                "error": str(error),
            },
        ) from error

    if respuesta.status_code >= 400:
        if datos_cache is not None:
            return datos_cache

        raise HTTPException(
            status_code=respuesta.status_code,
            detail={
                "mensaje": "Datos Abiertos Colombia rechazó la consulta.",
                "respuesta": respuesta.text[:500],
            },
        )

    try:
        registros = respuesta.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="El catálogo de municipios devolvió una respuesta inválida.",
        ) from error

    catalogo = []

    for registro in registros:
        normalizado = _normalizar_registro(registro)
        if normalizado:
            catalogo.append(normalizado)

    if not catalogo:
        raise HTTPException(
            status_code=502,
            detail="El catálogo de municipios llegó vacío.",
        )

    _cache["datos"] = catalogo
    _cache["actualizado_en"] = ahora
    return catalogo


async def listar_departamentos() -> list[dict]:
    catalogo = await obtener_catalogo_municipios()
    departamentos: dict[str, str] = {}

    for fila in catalogo:
        codigo = fila["codigo_departamento"]
        nombre = fila["departamento"]

        if codigo and nombre:
            departamentos[codigo] = nombre

    return [
        {
            "codigo_departamento": codigo,
            "departamento": nombre,
        }
        for codigo, nombre in sorted(
            departamentos.items(),
            key=lambda item: _texto_normalizado(item[1]),
        )
    ]


async def listar_municipios_por_departamento(
    codigo_departamento: str,
) -> list[dict]:
    catalogo = await obtener_catalogo_municipios()
    codigo = codigo_departamento.strip()

    municipios = [
        fila
        for fila in catalogo
        if fila["codigo_departamento"] == codigo
    ]

    if not municipios:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron municipios para el departamento indicado.",
        )

    return municipios


async def buscar_municipios(
    texto: str,
    limite: int = 20,
) -> list[dict]:
    consulta = _texto_normalizado(texto)

    if len(consulta) < 2:
        raise HTTPException(
            status_code=400,
            detail="Escribe al menos dos caracteres para buscar.",
        )

    catalogo = await obtener_catalogo_municipios()
    resultados = []

    for fila in catalogo:
        municipio = _texto_normalizado(fila["municipio"])
        departamento = _texto_normalizado(fila["departamento"])
        combinado = f"{municipio} {departamento}"

        if consulta in combinado:
            prioridad = 0 if municipio.startswith(consulta) else 1
            resultados.append((prioridad, fila))

    resultados.sort(
        key=lambda item: (
            item[0],
            _texto_normalizado(item[1]["municipio"]),
            _texto_normalizado(item[1]["departamento"]),
        )
    )

    return [fila for _, fila in resultados[:limite]]


async def obtener_municipio_por_codigo(
    codigo_municipio: str,
) -> dict:
    catalogo = await obtener_catalogo_municipios()
    codigo = codigo_municipio.strip()

    for fila in catalogo:
        if fila["codigo_municipio"] == codigo:
            return fila

    raise HTTPException(
        status_code=404,
        detail="No se encontró el municipio solicitado.",
    )
