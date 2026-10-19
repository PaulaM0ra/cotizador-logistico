from pathlib import Path

ruta = Path("app/services/peajes.py")
if not ruta.exists():
    raise SystemExit("ERROR: no se encontro app/services/peajes.py")

texto = ruta.read_text(encoding="utf-8")

# 1. Imports necesarios.
if "import ssl\n" not in texto:
    texto = texto.replace("import re\n", "import re\nimport ssl\n", 1)
if "import truststore\n" not in texto:
    texto = texto.replace("import httpx\n", "import httpx\nimport truststore\n", 1)

# 2. Sustituir la configuracion ANI singular por dos fuentes.
inicio_url = texto.find("ANI_GEO_URL = (")
if inicio_url == -1:
    inicio_url = texto.find("ANI_GEO_URLS = (")
fin_url = texto.find("\n\nCACHE_SEGUNDOS", inicio_url)
if inicio_url == -1 or fin_url == -1:
    raise SystemExit("ERROR: no se encontro el bloque ANI_GEO_URL")

bloque_urls = '''ANI_GEO_URLS = (
    "https://aniscopiosig-server.ani.gov.co/arcgisserver/rest/services/"
    "Hosted/ModosANI/FeatureServer/5/query",
    "https://sig.ani.gov.co/arcgissrv/rest/services/"
    "3_DatosAbiertos/OpenDataICDE/MapServer/0/query",
)'''
texto = texto[:inicio_url] + bloque_urls + texto[fin_url:]

# 3. Reemplazar el cliente HTTP con truststore para ANI.
inicio_json = texto.find("async def _consultar_json(")
fin_json = texto.find("\nasync def _consultar_socrata(", inicio_json)
if inicio_json == -1 or fin_json == -1:
    raise SystemExit("ERROR: no se encontro _consultar_json")

funcion_json = '''async def _consultar_json(
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
'''
texto = texto[:inicio_json] + funcion_json + texto[fin_json + 1:]

# 4. Reemplazar la consulta ANI por una version con fuente principal y respaldo.
inicio_ani = texto.find("async def obtener_peajes_geograficos_ani(")
fin_ani = texto.find("\nasync def obtener_tarifas_ani(", inicio_ani)
if inicio_ani == -1 or fin_ani == -1:
    raise SystemExit("ERROR: no se encontro obtener_peajes_geograficos_ani")

funcion_ani = '''async def obtener_peajes_geograficos_ani(
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
'''
texto = texto[:inicio_ani] + funcion_ani + texto[fin_ani + 1:]

# Validar antes de escribir.
compile(texto, str(ruta), "exec")
ruta.write_text(texto, encoding="utf-8")

print("[OK] ANI_GEO_URLS creada")
print("[OK] truststore aplicado a dominios ANI")
print("[OK] consulta ANI principal + respaldo configurada")
print("[OK] sintaxis validada")
