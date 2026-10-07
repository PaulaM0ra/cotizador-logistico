console.log("municipios-ui.js cargado correctamente");

document.addEventListener("DOMContentLoaded", function () {
    const origenLongitud = document.getElementById("origen-longitud");
    const destinoLongitud = document.getElementById("destino-longitud");

    if (!origenLongitud || !destinoLongitud) {
        console.error("No se encontraron los campos de coordenadas.");
        return;
    }

    const filaCoordenadas = origenLongitud.closest(".row");

    if (!filaCoordenadas) {
        console.error("No se encontró el contenedor de coordenadas.");
        return;
    }

    const bloqueMunicipios = document.createElement("div");
    bloqueMunicipios.className = "row g-3 mb-3";
    bloqueMunicipios.innerHTML = `
        <div class="col-12">
            <div class="alert alert-light border mb-0">
                Selecciona los municipios de origen y destino. Después puedes
                ajustar cada punto arrastrando los marcadores sobre el mapa.
            </div>
        </div>

        <div class="col-12">
            <h3 class="h6 text-success mb-2">Origen</h3>
        </div>

        <div class="col-12 col-md-6">
            <label for="origen-departamento" class="form-label">
                Departamento de origen
            </label>
            <select id="origen-departamento" class="form-select" required>
                <option value="">Cargando departamentos...</option>
            </select>
        </div>

        <div class="col-12 col-md-6">
            <label for="origen-municipio" class="form-label">
                Municipio de origen
            </label>
            <select id="origen-municipio" class="form-select" required disabled>
                <option value="">Selecciona un departamento</option>
            </select>
        </div>

        <div class="col-12 mt-3">
            <h3 class="h6 text-success mb-2">Destino</h3>
        </div>

        <div class="col-12 col-md-6">
            <label for="destino-departamento" class="form-label">
                Departamento de destino
            </label>
            <select id="destino-departamento" class="form-select" required>
                <option value="">Cargando departamentos...</option>
            </select>
        </div>

        <div class="col-12 col-md-6">
            <label for="destino-municipio" class="form-label">
                Municipio de destino
            </label>
            <select id="destino-municipio" class="form-select" required disabled>
                <option value="">Selecciona un departamento</option>
            </select>
        </div>

        <div class="col-12">
            <button
                id="alternar-coordenadas"
                type="button"
                class="btn btn-outline-secondary btn-sm"
            >
                Mostrar coordenadas avanzadas
            </button>
        </div>
    `;

    filaCoordenadas.parentNode.insertBefore(bloqueMunicipios, filaCoordenadas);

    const columnasCoordenadas = Array.from(filaCoordenadas.children);
    columnasCoordenadas.forEach(function (columna) {
        columna.classList.add("coordenada-avanzada", "d-none");
    });

    const origenDepartamento = document.getElementById("origen-departamento");
    const origenMunicipio = document.getElementById("origen-municipio");
    const destinoDepartamento = document.getElementById("destino-departamento");
    const destinoMunicipio = document.getElementById("destino-municipio");
    const botonCoordenadas = document.getElementById("alternar-coordenadas");

    function mostrarErrorMunicipios(mensaje) {
        const contenedor = document.getElementById("mensaje-error");
        if (contenedor) {
            contenedor.textContent = mensaje;
            contenedor.classList.remove("d-none");
        }
    }

    async function consultarJson(url) {
        const respuesta = await fetch(url);
        const contenido = await respuesta.json();

        if (!respuesta.ok) {
            const detalle = contenido?.detail;
            const mensaje = typeof detalle === "string"
                ? detalle
                : detalle?.mensaje || "No fue posible consultar los municipios.";
            throw new Error(mensaje);
        }

        return contenido;
    }

    function llenarDepartamentos(select, departamentos) {
        select.innerHTML = '<option value="">Selecciona un departamento</option>';

        departamentos.forEach(function (item) {
            const opcion = document.createElement("option");
            opcion.value = item.codigo_departamento;
            opcion.textContent = item.departamento;
            select.appendChild(opcion);
        });
    }

    function llenarMunicipios(select, municipios) {
        select.innerHTML = '<option value="">Selecciona un municipio</option>';

        municipios.forEach(function (item) {
            const opcion = document.createElement("option");
            opcion.value = item.codigo_municipio;
            opcion.textContent = item.municipio;
            opcion.dataset.latitud = item.latitud ?? "";
            opcion.dataset.longitud = item.longitud ?? "";
            opcion.dataset.departamento = item.departamento ?? "";
            select.appendChild(opcion);
        });

        select.disabled = false;
    }

    async function cargarMunicipios(codigoDepartamento, selectMunicipio) {
        selectMunicipio.disabled = true;
        selectMunicipio.innerHTML = '<option value="">Cargando municipios...</option>';

        if (!codigoDepartamento) {
            selectMunicipio.innerHTML = '<option value="">Selecciona un departamento</option>';
            return;
        }

        const contenido = await consultarJson(
            `/municipios/departamento/${encodeURIComponent(codigoDepartamento)}`
        );

        llenarMunicipios(selectMunicipio, contenido.municipios);
    }

    function aplicarMunicipio(tipo, selectMunicipio) {
        const opcion = selectMunicipio.selectedOptions[0];

        if (!opcion || !opcion.value) return;

        const latitud = Number(opcion.dataset.latitud);
        const longitud = Number(opcion.dataset.longitud);

        if (!Number.isFinite(latitud) || !Number.isFinite(longitud)) {
            mostrarErrorMunicipios(
                "El municipio seleccionado no tiene coordenadas válidas. " +
                "Selecciona el punto directamente en el mapa."
            );
            return;
        }

        document.getElementById(`${tipo}-latitud`).value = latitud.toFixed(6);
        document.getElementById(`${tipo}-longitud`).value = longitud.toFixed(6);

        if (tipo === "origen" && typeof colocarMarcadorOrigen === "function") {
            colocarMarcadorOrigen(latitud, longitud);
        }

        if (tipo === "destino" && typeof colocarMarcadorDestino === "function") {
            colocarMarcadorDestino(latitud, longitud);
        }

        if (typeof mapa !== "undefined") {
            mapa.setView([latitud, longitud], 11);
            setTimeout(function () {
                mapa.invalidateSize(true);
            }, 200);
        }
    }

    async function seleccionarPredeterminado(
        selectDepartamento,
        selectMunicipio,
        codigoDepartamento,
        codigoMunicipio,
        tipo
    ) {
        selectDepartamento.value = codigoDepartamento;
        await cargarMunicipios(codigoDepartamento, selectMunicipio);
        selectMunicipio.value = codigoMunicipio;
        aplicarMunicipio(tipo, selectMunicipio);
    }

    origenDepartamento.addEventListener("change", async function () {
        try {
            await cargarMunicipios(origenDepartamento.value, origenMunicipio);
        } catch (error) {
            mostrarErrorMunicipios(error.message);
        }
    });

    destinoDepartamento.addEventListener("change", async function () {
        try {
            await cargarMunicipios(destinoDepartamento.value, destinoMunicipio);
        } catch (error) {
            mostrarErrorMunicipios(error.message);
        }
    });

    origenMunicipio.addEventListener("change", function () {
        aplicarMunicipio("origen", origenMunicipio);
    });

    destinoMunicipio.addEventListener("change", function () {
        aplicarMunicipio("destino", destinoMunicipio);
    });

    botonCoordenadas.addEventListener("click", function () {
        const ocultas = columnasCoordenadas[0]?.classList.contains("d-none");

        columnasCoordenadas.forEach(function (columna) {
            columna.classList.toggle("d-none", !ocultas);
        });

        botonCoordenadas.textContent = ocultas
            ? "Ocultar coordenadas avanzadas"
            : "Mostrar coordenadas avanzadas";

        setTimeout(function () {
            if (typeof mapa !== "undefined") mapa.invalidateSize(true);
        }, 200);
    });

    (async function iniciarMunicipios() {
        try {
            const contenido = await consultarJson("/municipios/departamentos");
            llenarDepartamentos(origenDepartamento, contenido.departamentos);
            llenarDepartamentos(destinoDepartamento, contenido.departamentos);

            await seleccionarPredeterminado(
                origenDepartamento,
                origenMunicipio,
                "11",
                "11001",
                "origen"
            );

            await seleccionarPredeterminado(
                destinoDepartamento,
                destinoMunicipio,
                "25",
                "25290",
                "destino"
            );
        } catch (error) {
            console.error(error);
            mostrarErrorMunicipios(error.message);
        }
    })();
});
