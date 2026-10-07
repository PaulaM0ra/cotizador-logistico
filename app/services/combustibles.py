import os
import time
import unicodedata
from typing import Any

import certifi
import httpx
from fastapi import HTTPException


COMBUSTIBLES_URL = "https://www.datos.gov.co/resource/gjy9-tpph.json"
CACHE_SEGUNDOS = 21600

_cache: dict[str, Any] = {
    "datos": {},
    "actualizado_en": {},
}


def _normalizar_texto(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "")
    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return " ".join(texto.upper().strip().split())


def _a_float(valor: Any) -> float | None:
    if valor is None or valor == "":
        return None

    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _producto_coincide(producto_registro: str, producto_solicitado: str) -> bool:
    registro = _normalizar_texto(producto_registro)
    solicitado = _normalizar_texto(producto_solicitado)

    if solicitado == "ACPM":
        return "ACPM" in registro or "DIESEL" in registro

    if solicitado == "GASOLINA":
        return "GASOLINA" in registro and "EXTRA" not in registro

    return solicitado in registro


async def _consultar_registros_municipio(
    codigo_municipio: str,
    forzar_actualizacion: bool = False,
) -> list[dict]:
    codigo = codigo_municipio.strip()
    ahora = time.time()
    clave_cache = codigo

    if (
        not forzar_actualizacion
        and clave_cache in _cache["datos"]
        and ahora - _cache["actualizado_en"].get(clave_cache, 0) < CACHE_SEGUNDOS
    ):
        return _cache["datos"][clave_cache]

    headers = {}
    app_token = os.getenv("SOCRATA_APP_TOKEN")

    if app_token:
        headers["X-App-Token"] = app_token

    parametros = {
        "$limit": 5000,
        "$select": (
            "periodo,mes,codigo_departamento,departamento,"
            "codigo_municipio,municipio,nombre_comercial,"
            "producto,precio,estado"
        ),
        "$where": f"codigo_municipio='{codigo}'",
        "$order": "periodo DESC, mes DESC",
    }

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            verify=certifi.where(),
            trust_env=False,
        ) as cliente:
            respuesta = await cliente.get(
                COMBUSTIBLES_URL,
                params=parametros,
                headers=headers,
            )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail="La consulta de combustibles tardó demasiado en responder.",
        ) from error
    except httpx.RequestError as error:
        datos_cache = _cache["datos"].get(clave_cache)

        if datos_cache is not None:
            return datos_cache

        raise HTTPException(
            status_code=503,
            detail={
                "mensaje": "No fue posible consultar los precios de combustible.",
                "tipo_error": type(error).__name__,
                "error": str(error),
            },
        ) from error

    if respuesta.status_code >= 400:
        raise HTTPException(
            status_code=respuesta.status_code,
            detail={
                "mensaje": "Datos Abiertos Colombia rechazó la consulta de combustible.",
                "respuesta": respuesta.text[:500],
            },
        )

    try:
        registros = respuesta.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="La fuente de combustibles devolvió una respuesta inválida.",
        ) from error

    if not isinstance(registros, list):
        raise HTTPException(
            status_code=502,
            detail="El formato recibido para combustibles no es válido.",
        )

    _cache["datos"][clave_cache] = registros
    _cache["actualizado_en"][clave_cache] = ahora
    return registros


async def obtener_precio_combustible(
    codigo_municipio: str,
    producto: str,
) -> dict:
    producto_normalizado = _normalizar_texto(producto)

    if producto_normalizado not in {"ACPM", "GASOLINA"}:
        raise HTTPException(
            status_code=400,
            detail="El producto debe ser 'acpm' o 'gasolina'.",
        )

    registros = await _consultar_registros_municipio(codigo_municipio)

    candidatos = [
        registro
        for registro in registros
        if _producto_coincide(
            str(registro.get("producto", "")),
            producto_normalizado,
        )
        and _a_float(registro.get("precio")) is not None
    ]

    if not candidatos:
        raise HTTPException(
            status_code=404,
            detail=(
                "No se encontraron precios para el municipio y combustible "
                "seleccionados. Ingresa el precio manualmente."
            ),
        )

    periodos = []

    for registro in candidatos:
        try:
            periodo = int(float(registro.get("periodo", 0)))
            mes = int(float(registro.get("mes", 0)))
        except (TypeError, ValueError):
            continue

        periodos.append((periodo, mes))

    if not periodos:
        raise HTTPException(
            status_code=502,
            detail="Los registros encontrados no contienen un periodo válido.",
        )

    periodo_mas_reciente = max(periodos)
    periodo, mes = periodo_mas_reciente

    registros_periodo = []

    for registro in candidatos:
        try:
            registro_periodo = int(float(registro.get("periodo", 0)))
            registro_mes = int(float(registro.get("mes", 0)))
        except (TypeError, ValueError):
            continue

        if (registro_periodo, registro_mes) == periodo_mas_reciente:
            registros_periodo.append(registro)

    precios = [
        _a_float(registro.get("precio"))
        for registro in registros_periodo
    ]
    precios = [precio for precio in precios if precio is not None and precio > 0]

    if not precios:
        raise HTTPException(
            status_code=502,
            detail="No se encontraron precios numéricos válidos.",
        )

    precio_promedio = sum(precios) / len(precios)
    precio_minimo = min(precios)
    precio_maximo = max(precios)
    ejemplo = registros_periodo[0]

    return {
        "codigo_municipio": str(ejemplo.get("codigo_municipio", codigo_municipio)),
        "municipio": ejemplo.get("municipio", ""),
        "departamento": ejemplo.get("departamento", ""),
        "producto_solicitado": producto_normalizado.lower(),
        "producto_fuente": ejemplo.get("producto", ""),
        "precio_promedio": round(precio_promedio, 2),
        "precio_minimo": round(precio_minimo, 2),
        "precio_maximo": round(precio_maximo, 2),
        "cantidad_estaciones": len(precios),
        "periodo": periodo,
        "mes": mes,
        "fuente": "Ministerio de Minas y Energía - Datos Abiertos Colombia",
        "dataset": "precio mes combustible",
        "es_precio_vigente": False,
        "advertencia": (
            "El valor corresponde al periodo más reciente disponible en el "
            "dataset consultado. Debe validarse antes de usarlo como precio vigente."
        ),
    }
