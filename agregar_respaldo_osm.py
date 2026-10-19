from pathlib import Path

ruta = Path("app/services/peajes.py")
if not ruta.exists():
    raise SystemExit("ERROR: no se encontro app/services/peajes.py")

texto = ruta.read_text(encoding="utf-8")
respaldo = ruta.with_name("peajes_antes_osm.py")
respaldo.write_text(texto, encoding="utf-8")

if "OVERPASS_URL" not in texto:
    marcador = "CACHE_SEGUNDOS ="
    posicion = texto.find(marcador)
    if posicion == -1:
        raise SystemExit("ERROR: no se encontro CACHE_SEGUNDOS")
    texto = (
        texto[:posicion]
        + 'OVERPASS_URL = "https://overpass-api.de/api/interpreter"\n\n'
        + texto[posicion:]
    )

if "async def obtener_peajes_osm" not in texto:
    marcador = "async def detectar_peajes_en_ruta("
    posicion = texto.find(marcador)
    if posicion == -1:
        raise SystemExit("ERROR: no se encontro detectar_peajes_en_ruta")

    funcion = '''async def obtener_peajes_osm(
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


'''
    texto = texto[:posicion] + funcion + texto[posicion:]

llamada = '''        obtener_tarifas_ani(),
        return_exceptions=True,'''
reemplazo = '''        obtener_tarifas_ani(),
        obtener_peajes_osm(coordenadas_ruta),
        return_exceptions=True,'''
if llamada in texto and "obtener_peajes_osm(coordenadas_ruta)" not in texto:
    texto = texto.replace(llamada, reemplazo, 1)
elif "obtener_peajes_osm(coordenadas_ruta)" not in texto:
    raise SystemExit("ERROR: no se pudo agregar OSM al asyncio.gather")

marcador = '''    if not geograficos_invias and not geograficos_ani:
'''
bloque = '''    if isinstance(resultados[3], list):
        geograficos_osm = resultados[3]
    else:
        geograficos_osm = []
        errores_fuentes.append({
            "fuente": "OpenStreetMap geográfico",
            "error": _describir_error_fuente(resultados[3]),
        })

    if not geograficos_invias and not geograficos_ani and not geograficos_osm:
'''
if marcador in texto and "geograficos_osm = resultados[3]" not in texto:
    texto = texto.replace(marcador, bloque, 1)
elif "geograficos_osm = resultados[3]" not in texto:
    raise SystemExit("ERROR: no se pudo agregar el manejo de OSM")

texto = texto.replace(
    "geograficos = geograficos_invias + geograficos_ani",
    "geograficos = geograficos_invias + geograficos_ani + geograficos_osm",
    1,
)

marcador_fuentes = '''    if tarifas_ani:
        fuentes_consultadas.append("ANI - Tarifas de Peajes")
'''
reemplazo_fuentes = '''    if tarifas_ani:
        fuentes_consultadas.append("ANI - Tarifas de Peajes")
    if geograficos_osm:
        fuentes_consultadas.append("OpenStreetMap - ubicación de peajes")
'''
if marcador_fuentes in texto and "OpenStreetMap - ubicación de peajes" not in texto:
    texto = texto.replace(marcador_fuentes, reemplazo_fuentes, 1)

compile(texto, str(ruta), "exec")
ruta.write_text(texto, encoding="utf-8")

print("[OK] Respaldo creado:", respaldo)
print("[OK] OpenStreetMap agregado como fuente geográfica de respaldo")
print("[OK] Las tarifas continúan viniendo de ANI o INVÍAS")
print("[OK] Sintaxis validada")
