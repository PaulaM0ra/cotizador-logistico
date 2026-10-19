import asyncio
import math
import os
import re
import ssl
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

import certifi
import httpx
import truststore
from fastapi import HTTPException


# Fuente INVÍAS que entrega registros completos: nombre, coordenadas y tarifas.
PEAJES_GEOGRAFICOS_URL = (
    "https://www.datos.gov.co/resource/Peajes_Geo.json"
)

# Tarifas de concesiones administradas por ANI.
ANI_TARIFAS_URL = (
    "https://www.datos.gov.co/resource/7gj8-j6i3.json"
)

# Capa oficial ANI de peajes.
ANI_GEO_URLS = (
    "https://aniscopiosig-server.ani.gov.co/arcgisserver/rest/services/"
    "Hosted/ModosANI/FeatureServer/5/query",
    "https://sig.ani.gov.co/arcgissrv/rest/services/"
    "3_DatosAbiertos/OpenDataICDE/MapServer/0/query",
)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CACHE_SEGUNDOS = 21600
TOLERANCIA_PREDETERMINADA_KM = 3.0

CAMPOS_CATEGORIA_INVIAS = {
    "I": "categoria_i",
    "II": "categoria_ii",
    "III": "categoria_iii",
    "IV": "categoria_iv",
    "V": "categoria_v",
    "VI": "categoria_vi",
    "VII": "categoria_vii",
}

_cache: dict[str, Any] = {
    "geograficos": None,
    "tarifas_ani": None,
    "geograficos_ani": None,
    "actualizado_geograficos": 0.0,
    "actualizado_ani": 0.0,
    "actualizado_geograficos_ani": 0.0,
}


def _normalizar_texto(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "")
    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )
    texto = texto.upper().strip()
    texto = re.sub(
        r"\b(PEAJE|ESTACION|ESTACIÓN|DE|DEL|LA|EL)\b",
        " ",
        texto,
    )
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return " ".join(texto.split())


def _normalizar_clave(valor: str) -> str:
    return _normalizar_texto(valor).replace(" ", "")


def _obtener_campo(registro: dict, *nombres: str) -> Any:
    indice = {
        _normalizar_clave(str(clave)): valor
        for clave, valor in registro.items()
    }
    for nombre in nombres:
        clave = _normalizar_clave(nombre)
        if clave in indice:
            return indice[clave]
    return None


def _a_float(valor: Any) -> float | None:
    if valor is None or valor == "":
        return None

    texto = str(valor).strip().replace("$", "").replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+", texto):
        texto = texto.replace(",", "")
    elif texto.count(",") == 1 and "." not in texto:
        izquierda, derecha = texto.split(",")
        texto = izquierda + (derecha if len(derecha) == 3 else "." + derecha)
    else:
        texto = texto.replace(",", "")

    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def _fecha_iso(valor: Any) -> str | None:
    if not valor:
        return None
    texto = str(valor).strip()
    try:
        return datetime.fromisoformat(
            texto.replace("Z", "+00:00")
        ).date().isoformat()
    except ValueError:
        return texto[:10] if len(texto) >= 10 else texto


def _categoria_romana(valor: Any) -> str | None:
    texto = _normalizar_texto(str(valor or ""))
    equivalencias = {
        "1": "I", "01": "I", "I": "I", "CAT I": "I", "CATEGORIA I": "I",
        "2": "II", "02": "II", "II": "II", "CAT II": "II", "CATEGORIA II": "II",
        "3": "III", "03": "III", "III": "III", "CAT III": "III", "CATEGORIA III": "III",
        "4": "IV", "04": "IV", "IV": "IV", "CAT IV": "IV", "CATEGORIA IV": "IV",
        "5": "V", "05": "V", "V": "V", "CAT V": "V", "CATEGORIA V": "V",
        "6": "VI", "06": "VI", "VI": "VI", "CAT VI": "VI", "CATEGORIA VI": "VI",
        "7": "VII", "07": "VII", "VII": "VII", "CAT VII": "VII", "CATEGORIA VII": "VII",
    }
    if texto in equivalencias:
        return equivalencias[texto]
    coincidencia = re.search(r"\b(VII|VI|V|IV|III|II|I)\b", texto)
    return coincidencia.group(1) if coincidencia else None


def _extraer_coordenadas(registro: dict) -> tuple[float, float] | None:
    longitud = _a_float(
        _obtener_campo(registro, "longitud", "longitude", "lon", "lng", "x")
    )
    latitud = _a_float(
        _obtener_campo(registro, "latitud", "latitude", "lat", "y")
    )
    if longitud is not None and latitud is not None:
        return longitud, latitud

    punto = _obtener_campo(
        registro,
        "point",
        "punto",
        "coordenadas",
        "geometry",
        "geometria",
        "location",
    )

    if isinstance(punto, dict):
        coordenadas = punto.get("coordinates")
        if isinstance(coordenadas, (list, tuple)) and len(coordenadas) >= 2:
            longitud = _a_float(coordenadas[0])
            latitud = _a_float(coordenadas[1])
            if longitud is not None and latitud is not None:
                return longitud, latitud

        longitud = _a_float(
            punto.get("longitude")
            or punto.get("longitud")
            or punto.get("lng")
            or punto.get("x")
        )
        latitud = _a_float(
            punto.get("latitude")
            or punto.get("latitud")
            or punto.get("lat")
            or punto.get("y")
        )
        if longitud is not None and latitud is not None:
            return longitud, latitud

    valores = [punto] if isinstance(punto, str) else []
    valores.extend(valor for valor in registro.values() if isinstance(valor, str))
    for valor in valores:
        coincidencia = re.search(
            r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)",
            valor,
            re.IGNORECASE,
        )
        if coincidencia:
            return float(coincidencia.group(1)), float(coincidencia.group(2))

    return None


def _proyectar_km(
    longitud: float,
    latitud: float,
    latitud_referencia: float,
) -> tuple[float, float]:
    radio = 6371.0088
    x = math.radians(longitud) * radio * math.cos(
        math.radians(latitud_referencia)
    )
    y = math.radians(latitud) * radio
    return x, y


def _distancia_punto_segmento_km(
    punto: tuple[float, float],
    inicio: tuple[float, float],
    fin: tuple[float, float],
) -> float:
    longitud_p, latitud_p = punto
    longitud_a, latitud_a = inicio
    longitud_b, latitud_b = fin
    latitud_ref = (latitud_p + latitud_a + latitud_b) / 3

    px, py = _proyectar_km(longitud_p, latitud_p, latitud_ref)
    ax, ay = _proyectar_km(longitud_a, latitud_a, latitud_ref)
    bx, by = _proyectar_km(longitud_b, latitud_b, latitud_ref)

    ab_x, ab_y = bx - ax, by - ay
    ap_x, ap_y = px - ax, py - ay
    longitud_ab_cuadrada = ab_x**2 + ab_y**2
    if longitud_ab_cuadrada == 0:
        return math.hypot(px - ax, py - ay)

    factor = (ap_x * ab_x + ap_y * ab_y) / longitud_ab_cuadrada
    factor = max(0.0, min(1.0, factor))
    cercano_x = ax + factor * ab_x
    cercano_y = ay + factor * ab_y
    return math.hypot(px - cercano_x, py - cercano_y)


def _distancia_a_ruta_km(
    punto: tuple[float, float],
    coordenadas_ruta: list[list[float]],
) -> float:
    distancia_minima = float("inf")
    for indice in range(len(coordenadas_ruta) - 1):
        inicio = coordenadas_ruta[indice]
        fin = coordenadas_ruta[indice + 1]
        if len(inicio) < 2 or len(fin) < 2:
            continue
        distancia_minima = min(
            distancia_minima,
            _distancia_punto_segmento_km(
                punto,
                (float(inicio[0]), float(inicio[1])),
                (float(fin[0]), float(fin[1])),
            ),
        )
    return distancia_minima


async def _consultar_json(
    url: str,
    parametros: dict,
    headers: dict | None = None,
) -> Any:
    if ".ani.gov.co" in url:
        verificacion_ssl = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    else:
        verificacion_ssl = certifi.where()

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            verify=verificacion_ssl,
            trust_env=False,
            follow_redirects=True,
        ) as cliente:
            respuesta = await cliente.get(
                url,
                params=parametros,
                headers=headers or {},
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
                "mensaje": "No fue posible consultar la fuente oficial de peajes.",
                "tipo_error": type(error).__name__,
                "error": str(error),
                "url": url,
            },
        ) from error

    if respuesta.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "mensaje": "La fuente oficial de peajes rechazó la consulta.",
                "estado_origen": respuesta.status_code,
                "url": str(respuesta.request.url),
                "respuesta": respuesta.text[:500],
            },
        )

    try:
        return respuesta.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail={
                "mensaje": "La fuente de peajes devolvió una respuesta inválida.",
                "url": url,
                "respuesta": respuesta.text[:300],
            },
        ) from error
async def _consultar_socrata(url: str, parametros: dict) -> list[dict]:
    headers = {}
    token = os.getenv("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token

    datos = await _consultar_json(url, parametros, headers)
    if not isinstance(datos, list):
        raise HTTPException(
            status_code=502,
            detail="El formato recibido para peajes no es válido.",
        )
    return datos


async def obtener_peajes_geograficos(
    forzar_actualizacion: bool = False,
) -> list[dict]:
    ahora = time.time()
    if (
        not forzar_actualizacion
        and _cache["geograficos"] is not None
        and ahora - _cache["actualizado_geograficos"] < CACHE_SEGUNDOS
    ):
        return _cache["geograficos"]

    originales = await _consultar_socrata(
        PEAJES_GEOGRAFICOS_URL,
        {"$limit": 1000},
    )

    datos = []
    for registro in originales:
        coordenadas = _extraer_coordenadas(registro)
        if coordenadas is None:
            continue

        normalizado = dict(registro)
        normalizado.update({
            "nombre_peaje": (
                _obtener_campo(registro, "nombre_peaje", "peaje", "nombre")
                or "Peaje sin nombre"
            ),
            "longitud": coordenadas[0],
            "latitud": coordenadas[1],
            "ubicaci_n": _obtener_campo(
                registro,
                "ubicaci_n",
                "ubicacion",
            ) or "",
            "sector": _obtener_campo(registro, "sector") or "",
            "sentido": _obtener_campo(registro, "sentido") or "",
            "administrador": _obtener_campo(
                registro,
                "administrador",
            ) or "INVÍAS",
            "responsable": _obtener_campo(
                registro,
                "responsable",
            ) or "INVÍAS",
            "origen_geografico": "INVÍAS",
        })
        datos.append(normalizado)

    if not datos:
        raise HTTPException(
            status_code=502,
            detail={
                "mensaje": (
                    "La fuente de INVÍAS respondió, pero no entregó "
                    "peajes con coordenadas válidas."
                ),
                "registros_recibidos": len(originales),
            },
        )

    _cache["geograficos"] = datos
    _cache["actualizado_geograficos"] = ahora
    return datos


async def obtener_peajes_geograficos_ani(
    forzar_actualizacion: bool = False,
) -> list[dict]:
    ahora = time.time()
    if (
        not forzar_actualizacion
        and _cache["geograficos_ani"] is not None
        and ahora - _cache["actualizado_geograficos_ani"] < CACHE_SEGUNDOS
    ):
        return _cache["geograficos_ani"]

    errores = []
    parametros = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": 2000,
        "f": "json",
    }

    for url in ANI_GEO_URLS:
        try:
            contenido = await _consultar_json(url, parametros)
            if not isinstance(contenido, dict):
                errores.append({"url": url, "error": "Formato no valido"})
                continue
            if contenido.get("error"):
                errores.append({"url": url, "error": contenido["error"]})
                continue

            resultados = []
            for feature in contenido.get("features", []):
                originales = feature.get("attributes", {}) or {}
                atributos = {
                    _normalizar_clave(str(clave)): valor
                    for clave, valor in originales.items()
                }
                geometria = feature.get("geometry", {}) or {}

                longitud = _a_float(
                    atributos.get("LONGITUD")
                    or atributos.get("LONGITUDE")
                    or atributos.get("LON")
                    or geometria.get("x")
                )
                latitud = _a_float(
                    atributos.get("LATITUD")
                    or atributos.get("LATITUDE")
                    or atributos.get("LAT")
                    or geometria.get("y")
                )
                if longitud is None or latitud is None:
                    continue

                municipio = str(atributos.get("MUNICIPIO") or "").strip()
                departamento = str(atributos.get("DEPARTAMENTO") or "").strip()
                ubicacion = ", ".join(
                    valor for valor in (municipio, departamento) if valor
                )

                resultados.append({
                    "nombre_peaje": (
                        atributos.get("NOMBRE")
                        or atributos.get("NOMBREPEAJE")
                        or atributos.get("PEAJE")
                        or "Peaje ANI sin nombre"
                    ),
                    "codigo_peaje": (
                        atributos.get("IDPEA")
                        or atributos.get("IDPEAJE")
                        or atributos.get("OBJECTID")
                    ),
                    "estado": atributos.get("ESTADO") or "",
                    "proyecto": atributos.get("PROYECTO") or "",
                    "sector": atributos.get("CODVIA") or atributos.get("SECTOR") or "",
                    "ubicaci_n": ubicacion,
                    "sentido": atributos.get("SENTIDO") or "",
                    "administrador": "ANI",
                    "responsable": "ANI",
                    "longitud": longitud,
                    "latitud": latitud,
                    "origen_geografico": "ANI",
                })

            if resultados:
                _cache["geograficos_ani"] = resultados
                _cache["actualizado_geograficos_ani"] = ahora
                return resultados

            errores.append({
                "url": url,
                "error": "La fuente no entrego puntos con longitud y latitud.",
                "features_recibidos": len(contenido.get("features", [])),
            })
        except Exception as error:
            detalle = error.detail if isinstance(error, HTTPException) else str(error)
            errores.append({"url": url, "error": detalle})

    raise HTTPException(
        status_code=502,
        detail={
            "mensaje": "Ninguna fuente geográfica de ANI entregó peajes válidos.",
            "intentos": errores,
        },
    )
async def obtener_tarifas_ani(
    forzar_actualizacion: bool = False,
) -> list[dict]:
    ahora = time.time()
    if (
        not forzar_actualizacion
        and _cache["tarifas_ani"] is not None
        and ahora - _cache["actualizado_ani"] < CACHE_SEGUNDOS
    ):
        return _cache["tarifas_ani"]

    datos = await _consultar_socrata(
        ANI_TARIFAS_URL,
        {
            "$limit": 5000,
            "$select": (
                "idpeaje,peaje,ultimofechacambiopeaje,"
                "idcategoriatarifa,valor"
            ),
            "$order": "ultimofechacambiopeaje DESC",
        },
    )
    _cache["tarifas_ani"] = datos
    _cache["actualizado_ani"] = ahora
    return datos


def _indexar_tarifas_ani(registros: list[dict]) -> dict[str, list[dict]]:
    indice: dict[str, list[dict]] = {}
    for registro in registros:
        nombre = _normalizar_texto(str(registro.get("peaje", "")))
        categoria = _categoria_romana(registro.get("idcategoriatarifa"))
        valor = _a_float(registro.get("valor"))
        if not nombre or not categoria or valor is None or valor <= 0:
            continue

        indice.setdefault(nombre, []).append({
            "id_peaje_ani": registro.get("idpeaje"),
            "nombre": registro.get("peaje", ""),
            "nombre_normalizado": nombre,
            "categoria": categoria,
            "tarifa": valor,
            "fecha_tarifa": _fecha_iso(
                registro.get("ultimofechacambiopeaje")
            ),
        })
    return indice


def _buscar_tarifa_ani(
    nombre_peaje: str,
    categoria: str,
    indice_ani: dict[str, list[dict]],
) -> tuple[dict | None, float]:
    nombre = _normalizar_texto(nombre_peaje)
    if nombre in indice_ani:
        candidatos = [
            registro
            for registro in indice_ani[nombre]
            if registro["categoria"] == categoria
        ]
        if candidatos:
            candidatos.sort(
                key=lambda item: item.get("fecha_tarifa") or "",
                reverse=True,
            )
            return candidatos[0], 1.0

    similitudes = []
    for nombre_ani, registros in indice_ani.items():
        razon = SequenceMatcher(None, nombre, nombre_ani).ratio()
        if razon < 0.92:
            continue
        for candidato in registros:
            if candidato["categoria"] == categoria:
                similitudes.append((razon, candidato))

    if not similitudes:
        return None, 0.0

    similitudes.sort(
        key=lambda item: (
            item[0],
            item[1].get("fecha_tarifa") or "",
        ),
        reverse=True,
    )
    if (
        len(similitudes) > 1
        and abs(similitudes[0][0] - similitudes[1][0]) < 0.01
        and similitudes[0][1]["nombre_normalizado"]
        != similitudes[1][1]["nombre_normalizado"]
    ):
        return None, 0.0
    return similitudes[0][1], similitudes[0][0]


def _describir_error_fuente(error: BaseException) -> str:
    if isinstance(error, HTTPException):
        return str(error.detail)
    return str(error)


def _es_misma_estacion(
    primero: dict,
    segundo: dict,
) -> bool:
    nombre_primero = _normalizar_texto(primero["nombre"])
    nombre_segundo = _normalizar_texto(segundo["nombre"])
    nombres_iguales = nombre_primero == nombre_segundo
    distancia_entre_puntos = _distancia_punto_segmento_km(
        (primero["longitud"], primero["latitud"]),
        (segundo["longitud"], segundo["latitud"]),
        (segundo["longitud"], segundo["latitud"]),
    )
    return nombres_iguales or distancia_entre_puntos <= 0.15


async def obtener_peajes_osm(
    coordenadas_ruta: list[list[float]],
) -> list[dict]:
    """Obtiene cabinas y pórticos de peaje OSM cerca del corredor."""
    longitudes = [float(punto[0]) for punto in coordenadas_ruta if len(punto) >= 2]
    latitudes = [float(punto[1]) for punto in coordenadas_ruta if len(punto) >= 2]

    if not longitudes or not latitudes:
        return []

    margen = 0.12
    sur = min(latitudes) - margen
    oeste = min(longitudes) - margen
    norte = max(latitudes) + margen
    este = max(longitudes) + margen

    consulta = f"""
    [out:json][timeout:25];
    (
      node["barrier"="toll_booth"]({sur},{oeste},{norte},{este});
      node["highway"="toll_gantry"]({sur},{oeste},{norte},{este});
      way["barrier"="toll_booth"]({sur},{oeste},{norte},{este});
      way["highway"="toll_gantry"]({sur},{oeste},{norte},{este});
    );
    out center tags;
    """

    try:
        async with httpx.AsyncClient(
            timeout=35.0,
            verify=certifi.where(),
            trust_env=False,
            follow_redirects=True,
            headers={"User-Agent": "CotizadorLogisticoGA/1.0"},
        ) as cliente:
            respuesta = await cliente.post(
                OVERPASS_URL,
                data={"data": consulta},
            )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail="OpenStreetMap tardó demasiado en responder.",
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "mensaje": "No fue posible consultar OpenStreetMap.",
                "error": str(error),
            },
        ) from error

    if respuesta.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "mensaje": "OpenStreetMap rechazó la consulta de peajes.",
                "estado_origen": respuesta.status_code,
            },
        )

    contenido = respuesta.json()
    resultados = []

    for elemento in contenido.get("elements", []):
        etiquetas = elemento.get("tags", {}) or {}
        centro = elemento.get("center", {}) or {}
        latitud = _a_float(elemento.get("lat") or centro.get("lat"))
        longitud = _a_float(elemento.get("lon") or centro.get("lon"))
        if latitud is None or longitud is None:
            continue

        nombre = (
            etiquetas.get("name")
            or etiquetas.get("official_name")
            or etiquetas.get("operator")
            or f"Peaje OSM {elemento.get('id')}"
        )

        resultados.append({
            "nombre_peaje": nombre,
            "codigo_peaje": f"OSM-{elemento.get('id')}",
            "ubicaci_n": "",
            "sector": etiquetas.get("ref", ""),
            "sentido": "",
            "administrador": etiquetas.get("operator", ""),
            "responsable": etiquetas.get("operator", ""),
            "longitud": longitud,
            "latitud": latitud,
            "origen_geografico": "OpenStreetMap",
        })

    return resultados


async def detectar_peajes_en_ruta(
    geometria: dict,
    categoria: str = "I",
    tolerancia_km: float = TOLERANCIA_PREDETERMINADA_KM,
) -> dict:
    categoria_normalizada = _categoria_romana(categoria)
    if categoria_normalizada not in CAMPOS_CATEGORIA_INVIAS:
        raise HTTPException(
            status_code=400,
            detail="La categoría de peaje debe estar entre I y VII.",
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

    resultados = await asyncio.gather(
        obtener_peajes_geograficos(),
        obtener_peajes_geograficos_ani(),
        obtener_tarifas_ani(),
        obtener_peajes_osm(coordenadas_ruta),
        return_exceptions=True,
    )
    errores_fuentes = []

    if isinstance(resultados[0], list):
        geograficos_invias = resultados[0]
    else:
        geograficos_invias = []
        errores_fuentes.append({
            "fuente": "INVÍAS geográfico",
            "error": _describir_error_fuente(resultados[0]),
        })

    if isinstance(resultados[1], list):
        geograficos_ani = resultados[1]
    else:
        geograficos_ani = []
        errores_fuentes.append({
            "fuente": "ANI geográfico",
            "error": _describir_error_fuente(resultados[1]),
        })

    if isinstance(resultados[2], list):
        tarifas_ani = resultados[2]
    else:
        tarifas_ani = []
        errores_fuentes.append({
            "fuente": "ANI tarifas",
            "error": _describir_error_fuente(resultados[2]),
        })

    if isinstance(resultados[3], list):
        geograficos_osm = resultados[3]
    else:
        geograficos_osm = []
        errores_fuentes.append({
            "fuente": "OpenStreetMap geográfico",
            "error": _describir_error_fuente(resultados[3]),
        })

    if not geograficos_invias and not geograficos_ani and not geograficos_osm:
        raise HTTPException(
            status_code=503,
            detail={
                "mensaje": (
                    "No fue posible consultar ninguna fuente geográfica "
                    "de peajes. Usa temporalmente el modo manual."
                ),
                "fuentes": errores_fuentes,
            },
        )

    geograficos = geograficos_invias + geograficos_ani + geograficos_osm
    indice_ani = _indexar_tarifas_ani(tarifas_ani)
    campo_invias = CAMPOS_CATEGORIA_INVIAS[categoria_normalizada]
    encontrados = []
    diagnostico = []

    for registro in geograficos:
        coordenadas = _extraer_coordenadas(registro)
        if coordenadas is None:
            continue

        distancia_km = _distancia_a_ruta_km(
            coordenadas,
            coordenadas_ruta,
        )
        nombre = str(
            registro.get("nombre_peaje")
            or registro.get("peaje")
            or "Peaje sin nombre"
        ).strip()
        diagnostico.append({
            "nombre": nombre,
            "distancia_km": round(distancia_km, 3),
            "fuente": registro.get("origen_geografico", "INVÍAS"),
        })
        if distancia_km > tolerancia_km:
            continue

        tarifa_invias = _a_float(registro.get(campo_invias))
        tarifa_ani, confianza_ani = _buscar_tarifa_ani(
            nombre,
            categoria_normalizada,
            indice_ani,
        )

        if tarifa_ani is not None:
            tarifa = tarifa_ani["tarifa"]
            fuente_tarifa = "ANI - Tarifas de Peajes"
            fecha_tarifa = tarifa_ani.get("fecha_tarifa")
            coincidencia = "exacta" if confianza_ani == 1.0 else "nombre similar"
            requiere_validacion = confianza_ani < 1.0
        else:
            tarifa = tarifa_invias
            fuente_tarifa = "INVÍAS - Peajes Red Vial Nacional"
            fecha_tarifa = None
            coincidencia = "sin coincidencia ANI"
            requiere_validacion = tarifa is None or tarifa <= 0

        candidato = {
            "nombre": nombre,
            "codigo_peaje": (
                registro.get("c_digo_peaje")
                or registro.get("codigo_peaje")
            ),
            "ubicacion": registro.get("ubicaci_n", ""),
            "sector": registro.get("sector", ""),
            "sentido": registro.get("sentido", ""),
            "administrador": registro.get("administrador", ""),
            "responsable": registro.get("responsable", ""),
            "longitud": coordenadas[0],
            "latitud": coordenadas[1],
            "categoria": categoria_normalizada,
            "tarifa": tarifa,
            "tarifa_invias": tarifa_invias,
            "tarifa_ani": tarifa_ani["tarifa"] if tarifa_ani else None,
            "fuente_geografica": registro.get(
                "origen_geografico",
                "INVÍAS",
            ),
            "fuente_tarifa": fuente_tarifa,
            "fecha_tarifa": fecha_tarifa,
            "coincidencia_ani": coincidencia,
            "confianza_coincidencia_ani": round(confianza_ani, 3),
            "requiere_validacion": requiere_validacion,
            "distancia_a_ruta_km": round(distancia_km, 3),
        }

        duplicado = next(
            (
                existente
                for existente in encontrados
                if _es_misma_estacion(existente, candidato)
            ),
            None,
        )
        if duplicado is None:
            encontrados.append(candidato)
        elif duplicado.get("tarifa") is None and candidato.get("tarifa") is not None:
            encontrados.remove(duplicado)
            encontrados.append(candidato)

    encontrados.sort(key=lambda peaje: peaje["distancia_a_ruta_km"])
    diagnostico.sort(key=lambda peaje: peaje["distancia_km"])

    tarifas_validas = [
        float(peaje["tarifa"])
        for peaje in encontrados
        if peaje["tarifa"] is not None and peaje["tarifa"] > 0
    ]
    peajes_sin_tarifa = [
        peaje["nombre"]
        for peaje in encontrados
        if peaje["tarifa"] is None or peaje["tarifa"] <= 0
    ]

    fuentes_consultadas = []
    if geograficos_invias:
        fuentes_consultadas.append("INVÍAS - Peajes Red Vial Nacional")
    if geograficos_ani:
        fuentes_consultadas.append("ANI - Peajes geográficos")
    if tarifas_ani:
        fuentes_consultadas.append("ANI - Tarifas de Peajes")
    if geograficos_osm:
        fuentes_consultadas.append("OpenStreetMap - ubicación de peajes")

    advertencias = [
        "La detección usa proximidad geográfica y debe validarse antes "
        "de emitir una cotización definitiva."
    ]
    if errores_fuentes:
        advertencias.append(
            "Una o más fuentes externas no estuvieron disponibles; "
            "el cálculo continuó con las fuentes restantes."
        )
    if peajes_sin_tarifa:
        advertencias.append(
            "Hay peajes detectados sin tarifa para la categoría seleccionada."
        )

    return {
        "categoria": categoria_normalizada,
        "tolerancia_km": tolerancia_km,
        "cantidad_peajes": len(encontrados),
        "peajes": encontrados,
        "total_peajes_un_trayecto": round(sum(tarifas_validas), 2),
        "fuentes_consultadas": fuentes_consultadas,
        "fuentes_con_error": errores_fuentes,
        "peajes_mas_cercanos": diagnostico[:10],
        "peajes_sin_tarifa": peajes_sin_tarifa,
        "advertencia": " ".join(advertencias),
    }
