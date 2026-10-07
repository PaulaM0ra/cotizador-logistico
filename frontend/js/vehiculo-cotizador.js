import {
    initializeApp,
    getApps
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js";

import {
    getAuth,
    onAuthStateChanged
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";

const app = getApps().length
    ? getApps()[0]
    : initializeApp(window.FIREBASE_CONFIG);

const auth = getAuth(app);
let vehiculos = [];

function escapar(valor) {
    const elemento = document.createElement("div");
    elemento.textContent = valor ?? "";
    return elemento.innerHTML;
}

function nombreLegible(valor) {
    if (!valor) return "No definido";

    return valor
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letra) => letra.toUpperCase());
}

function dispararCambio(elemento) {
    elemento.dispatchEvent(
        new Event("change", { bubbles: true })
    );
}

async function consultarVehiculos() {
    const usuario = auth.currentUser;

    if (!usuario) return [];

    const token = await usuario.getIdToken();
    const respuesta = await fetch("/vehiculos", {
        headers: {
            Authorization: `Bearer ${token}`
        }
    });

    const contenido = await respuesta.json();

    if (!respuesta.ok) {
        const detalle = contenido?.detail;
        throw new Error(
            typeof detalle === "string"
                ? detalle
                : detalle?.mensaje
                    || "No fue posible consultar los vehículos."
        );
    }

    return contenido;
}

function insertarSelector() {
    if (document.getElementById("vehiculo-registrado")) return;

    const tipoVehiculo = document.getElementById("tipo-vehiculo");
    const fila = tipoVehiculo?.closest(".row");

    if (!fila) {
        console.error("No se encontró la sección de vehículo del cotizador.");
        return;
    }

    const bloque = document.createElement("div");
    bloque.className = "col-12 vehicle-selector-block";
    bloque.innerHTML = `
        <div class="vehicle-selector-card">
            <div class="vehicle-selector-heading">
                <div>
                    <label for="vehiculo-registrado" class="form-label mb-1">
                        Vehículo registrado
                    </label>
                    <p class="vehicle-selector-help mb-0">
                        Selecciona una placa para cargar categoría, combustible y rendimiento.
                    </p>
                </div>
                <a href="/mis-vehiculos" class="vehicle-manage-link">
                    Administrar vehículos
                </a>
            </div>

            <select id="vehiculo-registrado" class="form-select mt-3">
                <option value="">Selecciona un vehículo</option>
            </select>

            <div id="detalle-vehiculo-seleccionado" class="vehicle-selected-detail d-none"></div>
        </div>
    `;

    fila.insertBefore(bloque, fila.firstChild);

    document.getElementById("vehiculo-registrado").addEventListener(
        "change",
        aplicarVehiculoSeleccionado
    );
}

function llenarSelector() {
    const selector = document.getElementById("vehiculo-registrado");

    if (!selector) return;

    selector.innerHTML = '<option value="">Selecciona un vehículo</option>';

    vehiculos.forEach((vehiculo) => {
        const opcion = document.createElement("option");
        opcion.value = vehiculo.placa;
        opcion.textContent = `${vehiculo.placa} · ${nombreLegible(
            vehiculo.tipo_vehiculo
        )}`;
        selector.appendChild(opcion);
    });

    if (!vehiculos.length) {
        const opcion = document.createElement("option");
        opcion.disabled = true;
        opcion.textContent = "No tienes vehículos activos registrados";
        selector.appendChild(opcion);
    }
}

function tipoCompatibleCotizador(tipoRegistrado) {
    const livianos = new Set([
        "automovil",
        "camioneta",
        "campero",
        "motocarro"
    ]);

    return livianos.has(tipoRegistrado) ? "carro" : "camion";
}

function mostrarDetalle(vehiculo) {
    const detalle = document.getElementById(
        "detalle-vehiculo-seleccionado"
    );

    if (!detalle) return;

    if (!vehiculo) {
        detalle.classList.add("d-none");
        detalle.innerHTML = "";
        return;
    }

    detalle.innerHTML = `
        <div>
            <span>Placa</span>
            <strong>${escapar(vehiculo.placa)}</strong>
        </div>
        <div>
            <span>Tipo</span>
            <strong>${escapar(nombreLegible(vehiculo.tipo_vehiculo))}</strong>
        </div>
        <div>
            <span>Carrocería</span>
            <strong>${escapar(nombreLegible(
                vehiculo.tipo_carroceria || "sin_furgon"
            ))}</strong>
        </div>
        <div>
            <span>Ejes</span>
            <strong>${vehiculo.numero_ejes}</strong>
        </div>
        <div>
            <span>Categoría</span>
            <strong>${escapar(vehiculo.categoria_peaje)}</strong>
        </div>
        <div>
            <span>Capacidad</span>
            <strong>${vehiculo.capacidad_carga_kg} kg</strong>
        </div>
    `;
    detalle.classList.remove("d-none");
}

function aplicarVehiculoSeleccionado(evento) {
    const placa = evento.target.value;
    const vehiculo = vehiculos.find((item) => item.placa === placa);

    if (!vehiculo) {
        mostrarDetalle(null);
        return;
    }

    const tipoVehiculo = document.getElementById("tipo-vehiculo");
    const categoria = document.getElementById("categoria-peaje");
    const combustible = document.getElementById("tipo-combustible");
    const rendimiento = document.getElementById("rendimiento");

    tipoVehiculo.value = tipoCompatibleCotizador(
        vehiculo.tipo_vehiculo
    );
    categoria.value = vehiculo.categoria_peaje;
    combustible.value = vehiculo.tipo_combustible;
    rendimiento.value = vehiculo.rendimiento_km_galon;

    tipoVehiculo.dataset.placa = vehiculo.placa;
    tipoVehiculo.dataset.tipoRegistrado = vehiculo.tipo_vehiculo;
    tipoVehiculo.dataset.tipoCarroceria =
        vehiculo.tipo_carroceria || "sin_furgon";
    tipoVehiculo.dataset.numeroEjes = vehiculo.numero_ejes;

    dispararCambio(tipoVehiculo);
    dispararCambio(categoria);
    dispararCambio(combustible);
    dispararCambio(rendimiento);

    mostrarDetalle(vehiculo);
}

function agregarEstilos() {
    if (document.getElementById("estilos-selector-vehiculo")) return;

    const estilos = document.createElement("style");
    estilos.id = "estilos-selector-vehiculo";
    estilos.textContent = `
        .vehicle-selector-card {
            padding: 17px;
            border: 1px solid #dce6f2;
            border-radius: 14px;
            background: #f3f8ff;
        }

        .vehicle-selector-heading {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 14px;
        }

        .vehicle-selector-help {
            color: #6c7b91;
            font-size: .75rem;
        }

        .vehicle-manage-link {
            white-space: nowrap;
            color: #115bbb;
            font-size: .76rem;
            font-weight: 800;
            text-decoration: none;
        }

        .vehicle-selected-detail {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 8px;
            margin-top: 12px;
        }

        .vehicle-selected-detail div {
            padding: 9px;
            border-radius: 9px;
            background: #ffffff;
        }

        .vehicle-selected-detail span,
        .vehicle-selected-detail strong {
            display: block;
        }

        .vehicle-selected-detail span {
            color: #6c7b91;
            font-size: .68rem;
        }

        .vehicle-selected-detail strong {
            color: #08285c;
            font-size: .79rem;
        }

        @media (max-width: 600px) {
            .vehicle-selector-heading {
                flex-direction: column;
            }

            .vehicle-selected-detail {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
    `;

    document.head.appendChild(estilos);
}

onAuthStateChanged(auth, async (usuario) => {
    insertarSelector();
    agregarEstilos();

    const selector = document.getElementById("vehiculo-registrado");

    if (!usuario) {
        if (selector) {
            selector.innerHTML = `
                <option value="">
                    Inicia sesión para cargar tus vehículos
                </option>
            `;
            selector.disabled = true;
        }
        return;
    }

    try {
        vehiculos = await consultarVehiculos();
        selector.disabled = false;
        llenarSelector();
    } catch (error) {
        console.error(error);
        selector.innerHTML = `
            <option value="">
                No fue posible cargar los vehículos
            </option>
        `;
        selector.disabled = true;
    }
});
