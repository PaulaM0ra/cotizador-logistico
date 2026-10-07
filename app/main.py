from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.database.firebase import db
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.routes.cotizaciones import (
    router as cotizaciones_router
)
from app.routes.rutas import (
    router as rutas_router
)
from app.routes.vehiculos import (
    router as vehiculos_router
)
from app.routes.municipios import (
    router as municipios_router
)
from app.routes.combustibles import (
    router as combustibles_router
)
from app.routes.usuarios import (
    router as usuarios_router
)


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
CSS_DIR = FRONTEND_DIR / "css"
JS_DIR = FRONTEND_DIR / "js"


app = FastAPI(
    title="Cotizador Logístico G&A Distribuciones",
    description=(
        "API para calcular rutas y costos "
        "de distribución de mercancías."
    ),
    version="1.0.0"
)


app.include_router(vehiculos_router)
app.include_router(rutas_router)
app.include_router(cotizaciones_router)
app.include_router(municipios_router)
app.include_router(combustibles_router)
app.include_router(usuarios_router)

app.mount(
    "/frontend",
    StaticFiles(
        directory=str(FRONTEND_DIR)
    ),
    name="frontend"
)

app.mount(
    "/css",
    StaticFiles(
        directory=str(CSS_DIR)
    ),
    name="css"
)

app.mount(
    "/js",
    StaticFiles(
        directory=str(JS_DIR)
    ),
    name="js"
)


@app.get("/", tags=["Inicio"])
async def inicio():
    return {
        "mensaje": "API funcionando correctamente",
        "documentacion": "/docs",
        "mapa": "/mapa"
    }


@app.get("/mapa", include_in_schema=False)
async def mostrar_mapa():
    return FileResponse(
        str(FRONTEND_DIR / "index.html")
    )
@app.get("/acceso", include_in_schema=False)
async def mostrar_acceso():
    archivo_acceso = FRONTEND_DIR / "acceso.html"

    if not archivo_acceso.exists():
        raise HTTPException(
            status_code=404,
            detail="No se encontró frontend/acceso.html"
        )

    return FileResponse(
        str(archivo_acceso)
    )
@app.get("/mis-vehiculos", include_in_schema=False)
async def mostrar_vehiculos():
    archivo = FRONTEND_DIR / "vehiculos.html"

    if not archivo.exists():
        raise HTTPException(
            status_code=404,
            detail="No se encontró frontend/vehiculos.html"
        )

    return FileResponse(str(archivo))


@app.get("/salud", tags=["Inicio"])
async def verificar_salud():
    return {
        "estado": "activo"
    }
