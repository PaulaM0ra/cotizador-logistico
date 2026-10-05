const mapa = L.map("mapa").setView([4.5709, -74.2973], 9);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; colaboradores de OpenStreetMap"
}).addTo(mapa);

let capaRuta = null;
let marcadorOrigen = null;
let marcadorDestino = null;
let siguienteSeleccion = "origen";

const formulario = document.getElementById("form-ruta");
const botonCalcular = document.getElementById("boton-calcular");
const mensajeError = document.getElementById("mensaje-error");
const tarjetaResultado = document.getElementById("resultado");

function obtenerNumero(id) {
  return Number(document.getElementById(id).value);
}

function ponerOrigen(latitud, longitud) {
  if (marcadorOrigen) mapa.removeLayer(marcadorOrigen);

  marcadorOrigen = L.marker([latitud, longitud], { draggable: true })
    .addTo(mapa)
    .bindPopup("<strong>Origen</strong>");

  marcadorOrigen.on("dragend", (evento) => {
    const posicion = evento.target.getLatLng();
    document.getElementById("origen-latitud").value = posicion.lat.toFixed(6);
    document.getElementById("origen-longitud").value = posicion.lng.toFixed(6);
  });
}

function ponerDestino(latitud, longitud) {
  if (marcadorDestino) mapa.removeLayer(marcadorDestino);

  marcadorDestino = L.marker([latitud, longitud], { draggable: true })
    .addTo(mapa)
    .bindPopup("<strong>Destino</strong>");

  marcadorDestino.on("dragend", (evento) => {
    const posicion = evento.target.getLatLng();
    document.getElementById("destino-latitud").value = posicion.lat.toFixed(6);
    document.getElementById("destino-longitud").value = posicion.lng.toFixed(6);
  });
}

function actualizarMarcadores() {
  ponerOrigen(obtenerNumero("origen-latitud"), obtenerNumero("origen-longitud"));
  ponerDestino(obtenerNumero("destino-latitud"), obtenerNumero("destino-longitud"));
}

function ocultarError() {
  mensajeError.textContent = "";
  mensajeError.classList.add("d-none");
}

function mostrarError(texto) {
  mensajeError.textContent = texto;
  mensajeError.classList.remove("d-none");
}

function nombreCampoDesdeUbicacion(ubicacion) {
  const partes = Array.isArray(ubicacion) ? ubicacion : [];
  const seccion = partes.includes("origen") ? " del origen" : partes.includes("destino") ? " del destino" : "";
  const campo = partes.at(-1);

  const nombres = {
    latitud: `La latitud${seccion}`,
    longitud: `La longitud${seccion}`,
    tipo_vehiculo: "El tipo de vehículo"
  };

  return nombres[campo] || "Un campo";
}

function traducirErrorValidacion(error) {
  const campo = nombreCampoDesdeUbicacion(error.loc);
  const tipo = error.type || "";
  const limite = error.ctx?.le ?? error.ctx?.ge;

  if (tipo === "less_than_equal") return `${campo} debe ser menor o igual a ${limite}.`;
  if (tipo === "greater_than_equal") return `${campo} debe ser mayor o igual a ${limite}.`;
  if (tipo === "missing") return `${campo} es obligatorio.`;
  if (tipo.includes("float") || tipo.includes("number")) return `${campo} debe contener un número válido.`;

  return `${campo} contiene un valor inválido.`;
}

function obtenerMensajeError(contenido, estado) {
  if (Array.isArray(contenido?.detail)) {
    return contenido.detail.map(traducirErrorValidacion).join(" ");
  }

  if (typeof contenido?.detail === "string") return contenido.detail;
  if (contenido?.detail?.mensaje) return contenido.detail.mensaje;

  if (estado === 503) return "No fue posible conectarse con el servicio de rutas.";
  if (estado === 504) return "El servicio de rutas tardó demasiado en responder.";

  return "No fue posible calcular la ruta.";
}

formulario.addEventListener("submit", async (evento) => {
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
    tipo_vehiculo: document.getElementById("tipo-vehiculo").value
  };

  botonCalcular.disabled = true;
  botonCalcular.textContent = "Calculando...";

  try {
    const respuesta = await fetch("/rutas/calcular", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

    actualizarMarcadores();

    if (capaRuta) mapa.removeLayer(capaRuta);

    capaRuta = L.geoJSON(contenido.geometria, {
      style: {
        color: "#198754",
        weight: 6,
        opacity: 0.85
      }
    }).addTo(mapa);

    const limites = capaRuta.getBounds();
    if (limites.isValid()) mapa.fitBounds(limites, { padding: [30, 30] });

    document.getElementById("resultado-perfil").textContent = contenido.perfil;
    document.getElementById("resultado-distancia").textContent = contenido.distancia_km;
    document.getElementById("resultado-duracion").textContent = contenido.duracion_minutos;
    document.getElementById("resultado-horas").textContent = contenido.duracion_horas;
    tarjetaResultado.classList.remove("d-none");
  } catch (error) {
    mostrarError(error.message || "Ocurrió un error al calcular la ruta.");
  } finally {
    botonCalcular.disabled = false;
    botonCalcular.textContent = "Calcular ruta";
  }
});

mapa.on("click", (evento) => {
  const { lat, lng } = evento.latlng;

  if (siguienteSeleccion === "origen") {
    document.getElementById("origen-latitud").value = lat.toFixed(6);
    document.getElementById("origen-longitud").value = lng.toFixed(6);
    ponerOrigen(lat, lng);
    marcadorOrigen.openPopup();
    siguienteSeleccion = "destino";
  } else {
    document.getElementById("destino-latitud").value = lat.toFixed(6);
    document.getElementById("destino-longitud").value = lng.toFixed(6);
    ponerDestino(lat, lng);
    marcadorDestino.openPopup();
    siguienteSeleccion = "origen";
  }
});

actualizarMarcadores();
setTimeout(() => mapa.invalidateSize(), 200);
