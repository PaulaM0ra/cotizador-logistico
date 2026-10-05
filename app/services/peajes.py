import math
from typing import Any

import certifi
import httpx
from fastapi import HTTPException


PEAJES_URL = "https://www.datos.gov.co/resource/68qj-5xux.json"

CAMPOS_CATEGORIA = {
    "I": "categoria_i",
    "II": "categoria_ii",
    "III": "categoria_iii",
    "IV": "categoria_iv",
    "V": "categoria_v",
}


def _a_float(valor: Any) -> float | None:
    if valor is None or valor == "":
        return None

    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _extraer_coordenadas(peaje: dict) -> tuple[float, float] | None:
    punto = peaje.get("point") or peaje.get("location")

    if isinstance(punto, dict):
        coordenadas = punto.get("coordinates")

        if (
            isinstance(coordenadas, list)
            and len(coordenadas) >= 2
        ):
            longitud = _a_float(coordenadas[0])
            latitud = _a_float(coordenadas[1])

            if longitud is not None and latitud is not None:
                return longitud, latitud

        latitud = _a_float(
            punto.get("latitude") or punto.get("latitud")
        )
        longitud = _a_float(
            punto.get("longitude") or punto.get("longitud")
        )

        if latitud is not None and longitud is not None:
            return longitud, latitud

    latitud = _a_float(
        peaje.get("latitud") or peaje.get("latitude")
    )
    longitud = _a_float(
        peaje.get("longitud") or peaje.get("longitude")
    )

    if latitud is not None and longitud is not None:
        return longitud, latitud

    return None


def _proyectar_km(
    longitud: float,
    latitud: float,
    latitud_referencia: float,
) -> tuple[float, float]:
    radio_tierra_km = 6371.0088
    x = (
        math.radians(longitud)
        * radio_tierra_km
        * math.cos(math.radians(latitud_referencia))
    )
    y = math.radians(latitud) * radio_tierra_km
    return x, y


def _distancia_punto_segmento_km(
    punto: tuple[float, float],
    inicio: tuple[float, float],
    fin: tuple[float, float],
) -> float:
    longitud_p, latitud_p = punto
    longitud_a, latitud_a = inicio
    longitud_b, latitud_b = fin

    latitud_referencia = (latitud_p + latitud_a + latitud_b) / 3

    px, py = _proyectar_km(
        longitud_p,
        latitud_p,
        latitud_referencia,
    )
    ax, ay = _proyectar_km(
        longitud_a,
        latitud_a,
        latitud_referencia,
    )
    bx, by = _proyectar_km(
        longitud_b,
        latitud_b,
        latitud_referencia,
    )

    ab_x = bx - ax
    ab_y = by - ay
    ap_x = px - ax
    ap_y = py - ay

    longitud_ab_cuadrada = ab_x**2 + ab_y**2

    if longitud_ab_cuadrada == 0:
        return math.hypot(px - ax, py - ay)

    factor = (ap_x * ab_x + ap_y * ab_y) / longitud_ab_cuadrada
    factor = max(0.0, min(1.0, factor))

    punto_cercano_x = ax + factor * ab_x
    punto_cercano_y = ay + factor * ab_y

    return math.hypot(
        px - punto_cercano_x,
        py - punto_cercano_y,
    )


def _distancia_a_ruta_km(
    punto: tuple[float, float],
    coordenadas_ruta: list[list[float]],
) -> float:
    if len(coordenadas_ruta) < 2:
        raise HTTPException(
            status_code=400,
            detail="La geometría de la ruta no contiene suficientes puntos.",
        )

    distancia_minima = float("inf")

    for indice in range(len(coordenadas_ruta) - 1):
        inicio = coordenadas_ruta[indice]
        fin = coordenadas_ruta[indice + 1]

        if len(inicio) < 2 or len(fin) < 2:
            continue

        distancia = _distancia_punto_segmento_km(
            punto,
            (float(inicio[0]), float(inicio[1])),
            (float(fin[0]), float(fin[1])),
        )

        if distancia < distancia_minima:
            distancia_minima = distancia

    return distancia_minima


async def obtener_peajes_oficiales() -> list[dict]:
    parametros = {
        "$limit": 500,
        "$select": (
            "point,nombre_peaje,ubicaci_n,sector,sentido,"
            "categoria_i,categoria_ii,categoria_iii,"
            "categoria_iv,categoria_v"
        ),
    }

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            verify=certifi.where(),
            trust_env=False,
        ) as cliente:
            respuesta = await cliente.get(
                PEAJES_URL,
                params=parametros,
            )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail="La consulta de peajes tardó demasiado en responder.",
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "mensaje": "No fue posible consultar los peajes oficiales.",
                "tipo_error": type(error).__name__,
                "error": str(error),
            },
        ) from error

    if respuesta.status_code >= 400:
        raise HTTPException(
            status_code=respuesta.status_code,
            detail={
                "mensaje": "La fuente oficial de peajes rechazó la consulta.",
                "respuesta": respuesta.text[:500],
            },
        )

    try:
        datos = respuesta.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="La fuente de peajes devolvió una respuesta no válida.",
        ) from error

    if not isinstance(datos, list):
        raise HTTPException(
            status_code=502,
            detail="El formato recibido para los peajes no es válido.",
        )

    return datos


async def detectar_peajes_en_ruta(
    geometria: dict,
    categoria: str = "I",
    tolerancia_km: float = 0.8,
) -> dict:
    categoria_normalizada = categoria.strip().upper()

    if categoria_normalizada not in CAMPOS_CATEGORIA:
        raise HTTPException(
            status_code=400,
            detail="La categoría del peaje debe estar entre I y V.",
        )

    if not 0.1 <= tolerancia_km <= 5:
        raise HTTPException(
            status_code=400,
            detail="La tolerancia debe estar entre 0.1 y 5 kilómetros.",
        )

    if geometria.get("type") != "LineString":
        raise HTTPException(
            status_code=400,
            detail="La geometría debe ser de tipo LineString.",
        )

    coordenadas_ruta = geometria.get("coordinates", [])

    if len(coordenadas_ruta) < 2:
        raise HTTPException(
            status_code=400,
            detail="La ruta no contiene suficientes coordenadas.",
        )

    peajes_oficiales = await obtener_peajes_oficiales()
    campo_tarifa = CAMPOS_CATEGORIA[categoria_normalizada]
    encontrados: list[dict] = []
    claves_agregadas: set[str] = set()

    for peaje in peajes_oficiales:
        coordenadas_peaje = _extraer_coordenadas(peaje)

        if coordenadas_peaje is None:
            continue

        distancia_km = _distancia_a_ruta_km(
            coordenadas_peaje,
            coordenadas_ruta,
        )

        if distancia_km > tolerancia_km:
            continue

        nombre = (
            peaje.get("nombre_peaje")
            or peaje.get("peaje")
            or "Peaje sin nombre"
        ).strip()

        clave = (
            f"{nombre.lower()}|"
            f"{coordenadas_peaje[0]:.5f}|"
            f"{coordenadas_peaje[1]:.5f}"
        )

        if clave in claves_agregadas:
            continue

        tarifa = _a_float(peaje.get(campo_tarifa))

        encontrados.append(
            {
                "nombre": nombre,
                "ubicacion": peaje.get("ubicaci_n", ""),
                "sector": peaje.get("sector", ""),
                "sentido": peaje.get("sentido", ""),
                "longitud": coordenadas_peaje[0],
                "latitud": coordenadas_peaje[1],
                "categoria": categoria_normalizada,
                "tarifa": tarifa,
                "distancia_a_ruta_km": round(distancia_km, 3),
                "fuente": "Datos Abiertos Colombia - INVÍAS",
            }
        )
        claves_agregadas.add(clave)

    encontrados.sort(
        key=lambda peaje: peaje["distancia_a_ruta_km"]
    )

    tarifas_disponibles = [
        peaje["tarifa"]
        for peaje in encontrados
        if peaje["tarifa"] is not None
    ]

    return {
        "categoria": categoria_normalizada,
        "tolerancia_km": tolerancia_km,
        "cantidad_peajes": len(encontrados),
        "peajes": encontrados,
        "total_peajes_un_trayecto": round(
            sum(tarifas_disponibles),
            2,
        ),
        "advertencia": (
            "La detección se basa en proximidad geográfica. "
            "Debe validarse el sentido de cobro y cualquier tarifa diferencial."
        ),
    }
