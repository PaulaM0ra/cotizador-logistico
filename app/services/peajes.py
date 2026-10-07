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


# Geografía y tarifas publicadas por INVÍAS.
PEAJES_GEOGRAFICOS_URL = (
    "https://www.datos.gov.co/resource/ax36-cggc.json"
)

# Tarifas de concesiones administradas por ANI.
ANI_TARIFAS_URL = (
    "https://www.datos.gov.co/resource/7gj8-j6i3.json"
)

ANI_GEO_URL = (
    "https://aniscopiosig-server.ani.gov.co/arcgisserver/rest/services/"
    "Hosted/ModosANI/FeatureServer/5/query"
)

CACHE_SEGUNDOS = 21600

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
    texto = re.sub(r"\b(PEAJE|ESTACION|ESTACIÓN|DE|DEL|LA|EL)\b", " ", texto)
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return " ".join(texto.split())


def _a_float(valor: Any) -> float | None:
    if valor is None or valor == "":
        return None

    texto = str(valor).strip().replace("$", "").replace(" ", "")

    # En tarifas colombianas, una coma suele ser separador de miles.
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+", texto):
        texto = texto.replace(",", "")
    elif texto.count(",") == 1 and "." not in texto:
        izquierda, derecha = texto.split(",")
        if len(derecha) == 3:
            texto = izquierda + derecha
        else:
            texto = izquierda + "." + derecha
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
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return texto[:10] if len(texto) >= 10 else texto


def _categoria_romana(valor: Any) -> str | None:
    texto = _normalizar_texto(str(valor or ""))

    equivalencias = {
        "1": "I",
        "01": "I",
        "I": "I",
        "CAT I": "I",
        "CATEGORIA I": "I",
        "2": "II",
        "02": "II",
        "II": "II",
        "CAT II": "II",
        "CATEGORIA II": "II",
        "3": "III",
        "03": "III",
        "III": "III",
        "CAT III": "III",
        "CATEGORIA III": "III",
        "4": "IV",
        "04": "IV",
        "IV": "IV",
        "CAT IV": "IV",
        "CATEGORIA IV": "IV",
        "5": "V",
        "05": "V",
        "V": "V",
        "CAT V": "V",
        "CATEGORIA V": "V",
        "6": "VI",
        "06": "VI",
        "VI": "VI",
        "CAT VI": "VI",
        "CATEGORIA VI": "VI",
        "7": "VII",
        "07": "VII",
        "VII": "VII",
        "CAT VII": "VII",
        "CATEGORIA VII": "VII",
    }

    if texto in equivalencias:
        return equivalencias[texto]

    coincidencia = re.search(r"\b(VII|VI|V|IV|III|II|I)\b", texto)
    return coincidencia.group(1) if coincidencia else None


def _extraer_coordenadas(peaje: dict) -> tuple[float, float] | None:
    longitud = _a_float(peaje.get("longitud"))
    latitud = _a_float(peaje.get("latitud"))

    if longitud is not None and latitud is not None:
        return longitud, latitud

    punto = peaje.get("point")

    if isinstance(punto, dict):
        coordenadas = punto.get("coordinates")
        if isinstance(coordenadas, list) and len(coordenadas) >= 2:
            longitud = _a_float(coordenadas[0])
            latitud = _a_float(coordenadas[1])
            if longitud is not None and latitud is not None:
                return longitud, latitud

    if isinstance(punto, str):
        coincidencia = re.search(
            r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)",
            punto,
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
    latitud_ref = (latitud_p + latitud_a + latitud_b) / 3

    px, py = _proyectar_km(longitud_p, latitud_p, latitud_ref)
    ax, ay = _proyectar_km(longitud_a, latitud_a, latitud_ref)
    bx, by = _proyectar_km(longitud_b, latitud_b, latitud_ref)

    ab_x = bx - ax
    ab_y = by - ay
    ap_x = px - ax
    ap_y = py - ay
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

        distancia = _distancia_punto_segmento_km(
            punto,
            (float(inicio[0]), float(inicio[1])),
            (float(fin[0]), float(fin[1])),
        )
        distancia_minima = min(distancia_minima, distancia)

    return distancia_minima


async def _consultar_socrata(
    url: str,
    parametros: dict,
) -> list[dict]:
    headers = {}
    token = os.getenv("SOCRATA_APP_TOKEN")

    if token:
        headers["X-App-Token"] = token

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            verify=certifi.where(),
            trust_env=False,
        ) as cliente:
            respuesta = await cliente.get(
                url,
                params=parametros,
                headers=headers,
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
                "mensaje": "No fue posible consultar las fuentes oficiales de peajes.",
                "tipo_error": type(error).__name__,
                "error": str(error),
            },
        ) from error

    if respuesta.status_code >= 400:
        raise HTTPException(
            status_code=respuesta.status_code,
            detail={
                "mensaje": "La fuente oficial de peajes rechazó la consulta.",
                "url": str(respuesta.request.url),
                "respuesta": respuesta.text[:500],
            },
        )

    try:
        datos = respuesta.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="La fuente de peajes devolvió una respuesta inválida.",
        ) from error

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

    # Se omite $select porque los nombres API de algunas columnas con
    # tildes pueden variar entre versiones del conjunto de Socrata.
    # Pedir el registro completo evita respuestas 400 por campos inválidos.
    parametros = {
        "$limit": 1000,
    }

    datos = await _consultar_socrata(
        PEAJES_GEOGRAFICOS_URL,
        parametros,
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

    parametros = {
        "where": "1=1",
        "outFields": (
            "idpea,nombre,estado,proyecto,codvia,pr,"
            "departamento,municipio,longitud,latitud"
        ),
        "returnGeometry": "false",
        "f": "json",
    }

    try:
        contexto_ssl_sistema = truststore.SSLContext(
            ssl.PROTOCOL_TLS_CLIENT
        )

        async with httpx.AsyncClient(
            timeout=30.0,
            verify=contexto_ssl_sistema,
            trust_env=False,
        ) as cliente:
            respuesta = await cliente.get(
                ANI_GEO_URL,
                params=parametros,
            )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail="La consulta geográfica de ANI tardó demasiado.",
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "mensaje": "No fue posible consultar los peajes geográficos de ANI.",
                "tipo_error": type(error).__name__,
                "error": str(error),
            },
        ) from error

    if respuesta.status_code >= 400:
        raise HTTPException(
            status_code=respuesta.status_code,
            detail={
                "mensaje": "ANI rechazó la consulta geográfica de peajes.",
                "respuesta": respuesta.text[:500],
            },
        )

    contenido = respuesta.json()

    if contenido.get("error"):
        raise HTTPException(
            status_code=502,
            detail={
                "mensaje": "ANI devolvió un error geográfico.",
                "respuesta": contenido["error"],
            },
        )

    resultados = []

    for feature in contenido.get("features", []):
        atributos = feature.get("attributes", {})
        resultados.append(
            {
                "nombre_peaje": atributos.get("nombre"),
                "codigo_peaje": atributos.get("idpea"),
                "estado": atributos.get("estado"),
                "proyecto": atributos.get("proyecto"),
                "sector": atributos.get("codvia", ""),
                "ubicaci_n": (
                    f"{atributos.get('municipio', '')}, "
                    f"{atributos.get('departamento', '')}"
                ).strip(", "),
                "administrador": "ANI",
                "responsable": "ANI",
                "longitud": atributos.get("longitud"),
                "latitud": atributos.get("latitud"),
                "origen_geografico": "ANI",
            }
        )

    _cache["geograficos_ani"] = resultados
    _cache["actualizado_geograficos_ani"] = ahora
    return resultados


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

    parametros = {
        "$limit": 5000,
        "$select": (
            "idpeaje,peaje,ultimofechacambiopeaje,"
            "idcategoriatarifa,valor"
        ),
        "$order": "ultimofechacambiopeaje DESC",
    }

    datos = await _consultar_socrata(
        ANI_TARIFAS_URL,
        parametros,
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

        indice.setdefault(nombre, []).append(
            {
                "id_peaje_ani": registro.get("idpeaje"),
                "nombre": registro.get("peaje", ""),
                "nombre_normalizado": nombre,
                "categoria": categoria,
                "tarifa": valor,
                "fecha_tarifa": _fecha_iso(
                    registro.get("ultimofechacambiopeaje")
                ),
            }
        )

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

        if razon >= 0.92:
            candidatos = [
                registro
                for registro in registros
                if registro["categoria"] == categoria
            ]
            for candidato in candidatos:
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

    # Si existen dos coincidencias casi iguales, no se asume una unión segura.
    if (
        len(similitudes) > 1
        and abs(similitudes[0][0] - similitudes[1][0]) < 0.01
        and similitudes[0][1]["nombre_normalizado"]
        != similitudes[1][1]["nombre_normalizado"]
    ):
        return None, 0.0

    return similitudes[0][1], similitudes[0][0]


async def detectar_peajes_en_ruta(
    geometria: dict,
    categoria: str = "I",
    tolerancia_km: float = 0.8,
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

    geograficos_invias, geograficos_ani, tarifas_ani = await asyncio.gather(
        obtener_peajes_geograficos(),
        obtener_peajes_geograficos_ani(),
        obtener_tarifas_ani(),
    )

    geograficos = geograficos_invias + geograficos_ani
    indice_ani = _indexar_tarifas_ani(tarifas_ani)
    campo_invia = CAMPOS_CATEGORIA_INVIAS[categoria_normalizada]
    encontrados = []
    claves_agregadas: set[str] = set()

    for registro in geograficos:
        coordenadas = _extraer_coordenadas(registro)

        if coordenadas is None:
            continue

        distancia_km = _distancia_a_ruta_km(
            coordenadas,
            coordenadas_ruta,
        )

        if distancia_km > tolerancia_km:
            continue

        nombre = str(
            registro.get("nombre_peaje")
            or registro.get("peaje")
            or "Peaje sin nombre"
        ).strip()
        clave = (
            f"{_normalizar_texto(nombre)}|"
            f"{coordenadas[0]:.5f}|{coordenadas[1]:.5f}"
        )

        if clave in claves_agregadas:
            continue

        tarifa_invias = _a_float(registro.get(campo_invia))
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
            requiere_validacion = tarifa is None

        encontrados.append(
            {
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
                "tarifa_ani": (
                    tarifa_ani["tarifa"] if tarifa_ani else None
                ),
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
        )
        claves_agregadas.add(clave)

    encontrados.sort(
        key=lambda peaje: peaje["distancia_a_ruta_km"]
    )

    tarifas_validas = [
        peaje["tarifa"]
        for peaje in encontrados
        if peaje["tarifa"] is not None and peaje["tarifa"] > 0
    ]
    peajes_sin_tarifa = [
        peaje["nombre"]
        for peaje in encontrados
        if peaje["tarifa"] is None or peaje["tarifa"] <= 0
    ]

    return {
        "categoria": categoria_normalizada,
        "tolerancia_km": tolerancia_km,
        "cantidad_peajes": len(encontrados),
        "peajes": encontrados,
        "total_peajes_un_trayecto": round(sum(tarifas_validas), 2),
        "fuentes_consultadas": [
            "INVÍAS - Peajes Red Vial Nacional",
            "ANI - Peajes geográficos",
            "ANI - Tarifas de Peajes",
        ],
        "peajes_sin_tarifa": peajes_sin_tarifa,
        "advertencia": (
            "La detección usa proximidad geográfica. Las coincidencias ANI por "
            "nombre similar y el sentido de cobro deben validarse antes de emitir "
            "una cotización definitiva."
        ),
    }
