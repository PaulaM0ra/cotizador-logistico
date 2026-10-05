console.log("cotizacion.js cargado correctamente");

const mapa = L.map(
    "mapa",
    {
        center: [4.5709, -74.2973],
        zoom: 9,
        zoomControl: true
    }
);

const capaBase = L.tileLayer(
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        minZoom: 3,
        maxZoom: 19,
        tileSize: 256,
        detectRetina: false,
        attribution:
            "&copy; colaboradores de OpenStreetMap"
    }
);

capaBase.addTo(mapa);

mapa.whenReady(
    function () {
        console.log("Mapa Leaflet listo");

        setTimeout(
            function () {
                mapa.invalidateSize(true);
            },
            500
        );
    }
);
let capaRuta = null;
let marcadorOrigen = null;
let marcadorDestino = null;
let marcadoresPeajes = [];
let siguienteSeleccion = "origen";

const formulario = document.getElementById("form-cotizacion");
const botonCalcular = document.getElementById("boton-calcular");
const mensajeError = document.getElementById("mensaje-error");
const tarjetaResultado = document.getElementById("resultado");
const contenedorResumen = document.getElementById("resumen");
const selectorModoPeajes = document.getElementById("modo-peajes");
const campoValorPeajes = document.getElementById("valor-peajes");

function obtenerNumero(id) {
    return Number(document.getElementById(id).value);
}

function obtenerTexto(id) {
    return document.getElementById(id).value;
}

function formatearDinero(valor) {
    return new Intl.NumberFormat("es-CO", {
        style: "currency",
        currency: "COP",
        maximumFractionDigits: 0
    }).format(valor ?? 0);
}

function colocarMarcadorOrigen(latitud, longitud) {
    if (marcadorOrigen) {
        mapa.removeLayer(marcadorOrigen);
    }

    marcadorOrigen = L.marker([latitud, longitud], {
        draggable: true
    })
        .addTo(mapa)
        .bindPopup("<strong>Origen del viaje</strong>");

    marcadorOrigen.on("dragend", function (evento) {
        const posicion = evento.target.getLatLng();
        document.getElementById("origen-latitud").value = posicion.lat.toFixed(6);
        document.getElementById("origen-longitud").value = posicion.lng.toFixed(6);
    });
}

function colocarMarcadorDestino(latitud, longitud) {
    if (marcadorDestino) {
        mapa.removeLayer(marcadorDestino);
    }

    marcadorDestino = L.marker([latitud, longitud], {
        draggable: true
    })
        .addTo(mapa)
        .bindPopup("<strong>Destino del viaje</strong>");

    marcadorDestino.on("dragend", function (evento) {
        const posicion = evento.target.getLatLng();
        document.getElementById("destino-latitud").value = posicion.lat.toFixed(6);
        document.getElementById("destino-longitud").value = posicion.lng.toFixed(6);
    });
}

function actualizarMarcadoresDesdeFormulario() {
    colocarMarcadorOrigen(
        obtenerNumero("origen-latitud"),
        obtenerNumero("origen-longitud")
    );

    colocarMarcadorDestino(
        obtenerNumero("destino-latitud"),
        obtenerNumero("destino-longitud")
    );
}

function ocultarError() {
    mensajeError.textContent = "";
    mensajeError.classList.add("d-none");
}

function mostrarError(mensaje) {
    mensajeError.textContent = mensaje;
    mensajeError.classList.remove("d-none");
}

function obtenerNombreCampo(ubicacion) {
    const partes = Array.isArray(ubicacion) ? ubicacion : [];
    const campo = partes.at(-1);
    let complemento = "";

    if (partes.includes("origen")) complemento = " de origen";
    if (partes.includes("destino")) complemento = " de destino";

    const nombres = {
        latitud: `La latitud${complemento}`,
        longitud: `La longitud${complemento}`,
        tipo_vehiculo: "El tipo de vehículo",
        tipo_combustible: "El tipo de combustible",
        rendimiento_km_galon: "El rendimiento",
        precio_combustible_galon: "El precio del combustible",
        numero_trayectos: "El número de trayectos",
        categoria_peaje: "La categoría de peaje",
        usar_peajes_automaticos: "El modo de cálculo de peajes",
        valor_peajes: "El valor de los peajes",
        gastos_adicionales: "Los gastos adicionales",
        porcentaje_utilidad: "El porcentaje de utilidad"
    };

    return nombres[campo] || "Un campo";
}

function traducirErrorValidacion(error) {
    const campo = obtenerNombreCampo(error.loc);
    const tipo = error.type || "";

    if (tipo === "less_than_equal") {
        return `${campo} debe ser menor o igual a ${error.ctx?.le}.`;
    }
    if (tipo === "greater_than_equal") {
        return `${campo} debe ser mayor o igual a ${error.ctx?.ge}.`;
    }
    if (tipo === "greater_than") {
        return `${campo} debe ser mayor que ${error.ctx?.gt}.`;
    }
    if (tipo === "missing") {
        return `${campo} es obligatorio.`;
    }
    if (tipo.includes("float") || tipo.includes("number") || tipo.includes("int")) {
        return `${campo} debe contener un número válido.`;
    }
    if (tipo === "literal_error") {
        return `${campo} contiene una opción no permitida.`;
    }

    return `${campo} contiene un valor inválido.`;
}

function obtenerMensajeError(contenido, estado) {
    if (Array.isArray(contenido?.detail)) {
        return contenido.detail.map(traducirErrorValidacion).join(" ");
    }
    if (typeof contenido?.detail === "string") {
        return contenido.detail;
    }
    if (contenido?.detail?.mensaje) {
        return contenido.detail.mensaje;
    }
    if (estado === 503) {
        return "No fue posible conectarse con el servicio externo requerido.";
    }
    if (estado === 504) {
        return "El servicio externo tardó demasiado en responder.";
    }

    return "No fue posible calcular la cotización.";
}

function dibujarRuta(geometria) {
    if (capaRuta) {
        mapa.removeLayer(capaRuta);
    }

    capaRuta = L.geoJSON(geometria, {
        style: {
            color: "#198754",
            weight: 6,
            opacity: 0.85
        }
    }).addTo(mapa);

    setTimeout(function () {
        mapa.invalidateSize();
        const limites = capaRuta.getBounds();

        if (limites.isValid()) {
            mapa.fitBounds(limites, { padding: [30, 30] });
        }
    }, 200);
}

function limpiarMarcadoresPeajes() {
    marcadoresPeajes.forEach(function (marcador) {
        mapa.removeLayer(marcador);
    });
    marcadoresPeajes = [];
}

function mostrarPeajesEnMapa(peajes) {
    limpiarMarcadoresPeajes();

    if (!Array.isArray(peajes)) return;

    peajes.forEach(function (peaje) {
        if (!Number.isFinite(Number(peaje.latitud)) ||
            !Number.isFinite(Number(peaje.longitud))) {
            return;
        }

        const tarifa = peaje.tarifa == null
            ? "Tarifa no disponible"
            : formatearDinero(peaje.tarifa);

        const marcador = L.circleMarker(
            [Number(peaje.latitud), Number(peaje.longitud)],
            {
                radius: 7,
                color: "#dc3545",
                fillColor: "#dc3545",
                fillOpacity: 0.9,
                weight: 2
            }
        )
            .addTo(mapa)
            .bindPopup(`
                <strong>${peaje.nombre}</strong><br>
                Categoría: ${peaje.categoria}<br>
                Tarifa: ${tarifa}<br>
                ${peaje.sentido ? `Sentido: ${peaje.sentido}` : ""}
            `);

        marcadoresPeajes.push(marcador);
    });
}

function crearDato(titulo, valor, columnas = "col-md-4", claseAdicional = "") {
    return `
        <div class="${columnas}">
            <div class="dato-cotizacion ${claseAdicional}">
                <span>${titulo}</span>
                <strong>${valor}</strong>
            </div>
        </div>
    `;
}

function crearDetallePeajes(peajes) {
    if (!Array.isArray(peajes.detalle) || peajes.detalle.length === 0) {
        return `
            <div class="col-12 mt-3">
                <div class="alert alert-warning mb-0">
                    No se detectaron peajes dentro de la tolerancia configurada.
                    Puedes cambiar el cálculo a modo manual.
                </div>
            </div>
        `;
    }

    return peajes.detalle.map(function (peaje) {
        const tarifa = peaje.tarifa == null
            ? "Tarifa no disponible"
            : formatearDinero(peaje.tarifa);

        const ubicacion = peaje.ubicacion || "Ubicación no informada";
        const sentido = peaje.sentido ? ` · ${peaje.sentido}` : "";

        return `
            <div class="col-12 col-lg-6">
                <div class="dato-cotizacion">
                    <span>${peaje.nombre}</span>
                    <strong>Categoría ${peaje.categoria}: ${tarifa}</strong>
                    <small class="text-muted">${ubicacion}${sentido}</small>
                </div>
            </div>
        `;
    }).join("");
}

function mostrarResumen(datos) {
    const ruta = datos.ruta;
    const combustible = datos.combustible;
    const peajes = datos.peajes;
    const costos = datos.costos;

    const tipoCombustible = combustible.tipo === "acpm" ? "ACPM" : "Gasolina";
    const modoPeajes = peajes.modo_calculo === "automatico" ? "Automático" : "Manual";

    contenedorResumen.innerHTML =
        crearDato("Perfil de ruta", ruta.perfil) +
        crearDato("Distancia de un trayecto", `${ruta.distancia_un_trayecto_km} km`) +
        crearDato("Distancia total", `${ruta.distancia_total_km} km`) +
        crearDato("Tipo de combustible", tipoCombustible) +
        crearDato("Rendimiento", `${combustible.rendimiento_km_galon} km/galón`) +
        crearDato("Galones estimados", combustible.galones_estimados) +
        crearDato("Precio por galón", formatearDinero(combustible.precio_por_galon)) +
        crearDato("Costo de combustible", formatearDinero(combustible.costo_estimado)) +
        crearDato("Modo de peajes", modoPeajes) +
        crearDato("Categoría de peaje", peajes.categoria) +
        crearDato("Peajes detectados", peajes.cantidad_peajes) +
        crearDato("Peajes por trayecto", formatearDinero(peajes.valor_un_trayecto)) +
        crearDato("Costo total de peajes", formatearDinero(peajes.costo_total)) +
        crearDato("Otros gastos", formatearDinero(costos.gastos_adicionales)) +
        crearDato("Subtotal operativo", formatearDinero(costos.subtotal_operativo)) +
        crearDato(
            `Utilidad ${costos.porcentaje_utilidad}%`,
            formatearDinero(costos.valor_utilidad)
        ) +
        crearDato(
            "Valor final del viaje",
            formatearDinero(costos.valor_cotizado),
            "col-md-8",
            "total"
        ) +
        `
            <div class="col-12 mt-4">
                <h3 class="h6 text-success">Peajes detectados</h3>
            </div>
        ` +
        crearDetallePeajes(peajes);

    tarjetaResultado.classList.remove("d-none");
}

async function consultarCotizacion(datos) {
    const respuesta = await fetch("/cotizaciones/calcular", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(datos)
    });

    let contenido;

    try {
        contenido = await respuesta.json();
    } catch {
        throw new Error("El servidor devolvió una respuesta no válida.");
    }

    if (!respuesta.ok) {
        throw new Error(obtenerMensajeError(contenido, respuesta.status));
    }

    return contenido;
}

formulario.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    ocultarError();

    if (!formulario.checkValidity()) {
        formulario.reportValidity();
        return;
    }

    const datos = {
        origen: {
            longitud: obtenerNumero("origen-longitud"),
            latitud: obtenerNumero("origen-latitud")
        },
        destino: {
            longitud: obtenerNumero("destino-longitud"),
            latitud: obtenerNumero("destino-latitud")
        },
        tipo_vehiculo: obtenerTexto("tipo-vehiculo"),
        tipo_combustible: obtenerTexto("tipo-combustible"),
        rendimiento_km_galon: obtenerNumero("rendimiento"),
        precio_combustible_galon: obtenerNumero("precio-combustible"),
        numero_trayectos: obtenerNumero("numero-trayectos"),
        categoria_peaje: obtenerTexto("categoria-peaje"),
        usar_peajes_automaticos: obtenerTexto("modo-peajes") === "automatico",
        valor_peajes: obtenerNumero("valor-peajes"),
        gastos_adicionales: obtenerNumero("gastos-adicionales"),
        porcentaje_utilidad: obtenerNumero("porcentaje-utilidad")
    };

    botonCalcular.disabled = true;
    botonCalcular.textContent = "Calculando...";

    try {
        const resultado = await consultarCotizacion(datos);
        actualizarMarcadoresDesdeFormulario();
        dibujarRuta(resultado.ruta.geometria);
        mostrarPeajesEnMapa(resultado.peajes.detalle);
        mostrarResumen(resultado);
    } catch (error) {
        console.error(error);
        mostrarError(
            error.message || "Ocurrió un error al calcular la cotización."
        );
    } finally {
        botonCalcular.disabled = false;
        botonCalcular.textContent = "Calcular cotización";
    }
});

mapa.on("click", function (evento) {
    const latitud = evento.latlng.lat;
    const longitud = evento.latlng.lng;

    if (siguienteSeleccion === "origen") {
        document.getElementById("origen-latitud").value = latitud.toFixed(6);
        document.getElementById("origen-longitud").value = longitud.toFixed(6);
        colocarMarcadorOrigen(latitud, longitud);
        marcadorOrigen.openPopup();
        siguienteSeleccion = "destino";
    } else {
        document.getElementById("destino-latitud").value = latitud.toFixed(6);
        document.getElementById("destino-longitud").value = longitud.toFixed(6);
        colocarMarcadorDestino(latitud, longitud);
        marcadorDestino.openPopup();
        siguienteSeleccion = "origen";
    }
});

document.getElementById("tipo-combustible").addEventListener(
    "change",
    function (evento) {
        const precioCombustible = document.getElementById("precio-combustible");

        if (evento.target.value === "acpm") {
            precioCombustible.value = 11616;
        } else if (evento.target.value === "gasolina") {
            precioCombustible.value = 16331;
        }
    }
);

function actualizarModoPeajes() {
    const automatico = selectorModoPeajes.value === "automatico";
    campoValorPeajes.disabled = automatico;

    if (automatico) {
        campoValorPeajes.value = 0;
    }
}

selectorModoPeajes.addEventListener("change", actualizarModoPeajes);

actualizarMarcadoresDesdeFormulario();
actualizarModoPeajes();

setTimeout(function () {
    mapa.invalidateSize();
}, 200);
