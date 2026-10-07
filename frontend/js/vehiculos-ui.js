import {
    initializeApp,
    getApps
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js";

import {
    getAuth,
    onAuthStateChanged,
    signOut
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";

const app = getApps().length
    ? getApps()[0]
    : initializeApp(window.FIREBASE_CONFIG);

const auth = getAuth(app);

let placaEditando = null;
let vehiculosActuales = [];

const formulario = document.getElementById("form-vehiculo");
const mensaje = document.getElementById("mensaje-vehiculos");
const lista = document.getElementById("lista-vehiculos");
const estadoLista = document.getElementById("estado-lista");

function mostrarMensaje(textoMensaje, tipo = "danger") {
    mensaje.textContent = textoMensaje;
    mensaje.className = `alert alert-${tipo}`;
    mensaje.classList.remove("d-none");
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function limpiarMensaje() {
    mensaje.classList.add("d-none");
    mensaje.textContent = "";
}

function numero(id) {
    return Number(document.getElementById(id).value);
}

function texto(id) {
    return document.getElementById(id).value.trim();
}

function nombreLegible(valor) {
    if (!valor) return "No definido";

    return valor
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letra) => letra.toUpperCase());
}

function escapar(valor) {
    const elemento = document.createElement("div");
    elemento.textContent = valor ?? "";
    return elemento.innerHTML;
}

async function api(ruta, opciones = {}) {
    const usuario = auth.currentUser;

    if (!usuario) {
        throw new Error("Debes iniciar sesión.");
    }

    const token = await usuario.getIdToken();
    const headers = new Headers(opciones.headers || {});

    headers.set("Authorization", `Bearer ${token}`);

    if (opciones.body) {
        headers.set("Content-Type", "application/json");
    }

    const respuesta = await fetch(ruta, {
        ...opciones,
        headers
    });

    let contenido = null;

    try {
        contenido = await respuesta.json();
    } catch {
        contenido = null;
    }

    if (!respuesta.ok) {
        const detalle = contenido?.detail;

        if (Array.isArray(detalle)) {
            throw new Error(
                detalle
                    .map((error) => error.msg)
                    .filter(Boolean)
                    .join(" ") || "Los datos enviados no son válidos."
            );
        }

        throw new Error(
            typeof detalle === "string"
                ? detalle
                : detalle?.mensaje
                    || "No fue posible completar la operación."
        );
    }

    return contenido;
}

function datosFormulario() {
    return {
        placa: texto("placa"),
        tipo_vehiculo: texto("tipo-vehiculo-registro"),
        tipo_carroceria: texto("tipo-carroceria"),
        numero_ejes: numero("numero-ejes"),
        categoria_peaje: texto("categoria-peaje-registro"),
        tipo_combustible: texto("tipo-combustible-registro"),
        rendimiento_km_galon: numero("rendimiento-registro"),
        capacidad_carga_kg: numero("capacidad-carga"),
        dimensiones: {
            largo_metros: numero("largo"),
            ancho_metros: numero("ancho"),
            alto_metros: numero("alto")
        },
        observaciones: texto("observaciones") || null
    };
}

function renderizar() {
    lista.innerHTML = "";

    const hayVehiculos = vehiculosActuales.length > 0;
    estadoLista.classList.toggle("d-none", hayVehiculos);
    estadoLista.textContent = hayVehiculos
        ? ""
        : "Todavía no tienes vehículos activos registrados.";

    vehiculosActuales.forEach((vehiculo) => {
        const tarjeta = document.createElement("article");
        tarjeta.className = "vehicle-card";

        const tipoVehiculo = escapar(
            nombreLegible(vehiculo.tipo_vehiculo)
        );

        const tipoCarroceria = escapar(
            nombreLegible(
                vehiculo.tipo_carroceria || "sin_furgon"
            )
        );

        tarjeta.innerHTML = `
            <div class="vehicle-card-header">
                <span class="plate">${escapar(vehiculo.placa)}</span>
                <span class="status">Activo</span>
            </div>

            <div class="vehicle-title">
                ${tipoVehiculo} · ${vehiculo.numero_ejes} ejes
            </div>

            <div class="vehicle-data">
                <div>
                    <span>Carrocería</span>
                    <strong>${tipoCarroceria}</strong>
                </div>

                <div>
                    <span>Categoría</span>
                    <strong>${escapar(vehiculo.categoria_peaje)}</strong>
                </div>

                <div>
                    <span>Combustible</span>
                    <strong>${escapar(
                        vehiculo.tipo_combustible.toUpperCase()
                    )}</strong>
                </div>

                <div>
                    <span>Rendimiento</span>
                    <strong>
                        ${vehiculo.rendimiento_km_galon} km/gal
                    </strong>
                </div>

                <div>
                    <span>Capacidad</span>
                    <strong>${vehiculo.capacidad_carga_kg} kg</strong>
                </div>

                <div>
                    <span>Dimensiones</span>
                    <strong>
                        ${vehiculo.dimensiones.largo_metros}
                        × ${vehiculo.dimensiones.ancho_metros}
                        × ${vehiculo.dimensiones.alto_metros} m
                    </strong>
                </div>
            </div>

            <div class="card-actions">
                <button
                    class="edit-button"
                    data-edit="${escapar(vehiculo.placa)}"
                    type="button"
                >
                    Editar
                </button>

                <button
                    class="disable-button"
                    data-disable="${escapar(vehiculo.placa)}"
                    type="button"
                >
                    Desactivar
                </button>
            </div>
        `;

        lista.appendChild(tarjeta);
    });
}

async function cargarVehiculos() {
    vehiculosActuales = await api("/vehiculos");
    renderizar();
}

function reiniciarFormulario() {
    formulario.reset();

    document.getElementById("numero-ejes").value = 2;
    document.getElementById("rendimiento-registro").value = 10;
    document.getElementById("capacidad-carga").value = 0;
    document.getElementById("tipo-carroceria").value = "sin_furgon";

    placaEditando = null;

    document.getElementById("placa").readOnly = false;
    document.getElementById("titulo-formulario").textContent =
        "Registrar vehículo";
    document.getElementById("guardar-vehiculo").textContent =
        "Guardar vehículo";
    document.getElementById("cancelar-edicion").classList.add("d-none");

    sugerirCategoria();
}

function editar(placa) {
    const vehiculo = vehiculosActuales.find(
        (item) => item.placa === placa
    );

    if (!vehiculo) return;

    placaEditando = placa;

    document.getElementById("placa").value = vehiculo.placa;
    document.getElementById("placa").readOnly = true;
    document.getElementById("tipo-vehiculo-registro").value =
        vehiculo.tipo_vehiculo;
    document.getElementById("tipo-carroceria").value =
        vehiculo.tipo_carroceria || "sin_furgon";
    document.getElementById("numero-ejes").value =
        vehiculo.numero_ejes;
    document.getElementById("categoria-peaje-registro").value =
        vehiculo.categoria_peaje;
    document.getElementById("tipo-combustible-registro").value =
        vehiculo.tipo_combustible;
    document.getElementById("rendimiento-registro").value =
        vehiculo.rendimiento_km_galon;
    document.getElementById("capacidad-carga").value =
        vehiculo.capacidad_carga_kg;
    document.getElementById("largo").value =
        vehiculo.dimensiones.largo_metros;
    document.getElementById("ancho").value =
        vehiculo.dimensiones.ancho_metros;
    document.getElementById("alto").value =
        vehiculo.dimensiones.alto_metros;
    document.getElementById("observaciones").value =
        vehiculo.observaciones || "";

    document.getElementById("titulo-formulario").textContent =
        `Editar ${vehiculo.placa}`;
    document.getElementById("guardar-vehiculo").textContent =
        "Guardar cambios";
    document.getElementById("cancelar-edicion").classList.remove("d-none");

    window.scrollTo({ top: 250, behavior: "smooth" });
}

function sugerirCategoria() {
    const tipo = texto("tipo-vehiculo-registro");
    const ejesCampo = document.getElementById("numero-ejes");
    const categoriaCampo = document.getElementById(
        "categoria-peaje-registro"
    );
    const ayuda = document.getElementById("ayuda-categoria");

    const configuraciones = {
        automovil: { ejes: 2, categoria: "I" },
        camioneta: { ejes: 2, categoria: "I" },
        campero: { ejes: 2, categoria: "I" },
        motocarro: { ejes: 2, categoria: "I" },
        furgon_ultraliviano: { ejes: 2, categoria: "II" },
        turbo_liviana: { ejes: 2, categoria: "II" },
        turbo_pesada: { ejes: 2, categoria: "II" },
        bus: { ejes: 2, categoria: "II" },
        buseta: { ejes: 2, categoria: "II" },
        microbus: { ejes: 2, categoria: "II" },
        camion_sencillo: { ejes: 2, categoria: "III" },
        doble_troque: { ejes: 3, categoria: "III" },
        cuatro_manos: { ejes: 4, categoria: "III" },
        mini_mula: { ejes: 4, categoria: "III" },
        tractocamion: { ejes: 5, categoria: "IV" },
        tractomula: { ejes: 6, categoria: "V" }
    };

    const configuracion = configuraciones[tipo];

    if (!configuracion) {
        ayuda.textContent =
            "Selecciona manualmente la categoría aplicable.";
        return;
    }

    ejesCampo.value = configuracion.ejes;
    categoriaCampo.value = configuracion.categoria;

    ayuda.textContent =
        `Sugerencia: ${configuracion.ejes} ejes, categoría `
        + `${configuracion.categoria}. Confirma la categoría aplicable `
        + "en la estación de peaje.";
}

formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    limpiarMensaje();

    try {
        const datos = datosFormulario();

        if (placaEditando) {
            delete datos.placa;

            await api(
                `/vehiculos/${encodeURIComponent(placaEditando)}`,
                {
                    method: "PATCH",
                    body: JSON.stringify(datos)
                }
            );

            mostrarMensaje(
                "Vehículo actualizado correctamente.",
                "success"
            );
        } else {
            await api("/vehiculos", {
                method: "POST",
                body: JSON.stringify(datos)
            });

            mostrarMensaje(
                "Vehículo registrado correctamente.",
                "success"
            );
        }

        reiniciarFormulario();
        await cargarVehiculos();
    } catch (error) {
        console.error(error);
        mostrarMensaje(error.message);
    }
});

lista.addEventListener("click", async (evento) => {
    const boton = evento.target.closest("button");

    if (!boton) return;

    const editarPlaca = boton.dataset.edit;
    const desactivarPlaca = boton.dataset.disable;

    if (editarPlaca) {
        editar(editarPlaca);
        return;
    }

    if (!desactivarPlaca) return;

    const confirmado = window.confirm(
        `¿Desactivar el vehículo ${desactivarPlaca}?`
    );

    if (!confirmado) return;

    try {
        await api(
            `/vehiculos/${encodeURIComponent(desactivarPlaca)}`,
            { method: "DELETE" }
        );

        mostrarMensaje("Vehículo desactivado.", "success");
        await cargarVehiculos();
    } catch (error) {
        mostrarMensaje(error.message);
    }
});

document.getElementById("cancelar-edicion").addEventListener(
    "click",
    reiniciarFormulario
);

document.getElementById("tipo-vehiculo-registro").addEventListener(
    "change",
    sugerirCategoria
);

document.getElementById("cerrar-sesion").addEventListener(
    "click",
    async () => {
        await signOut(auth);
        window.location.href = "/acceso";
    }
);

onAuthStateChanged(auth, async (usuario) => {
    if (!usuario) {
        window.location.href = "/acceso";
        return;
    }

    document.getElementById("usuario-email").textContent =
        usuario.email || usuario.uid;

    try {
        await cargarVehiculos();
        sugerirCategoria();
    } catch (error) {
        console.error(error);
        mostrarMensaje(error.message);
        estadoLista.textContent = "No fue posible cargar los vehículos.";
    }
});
