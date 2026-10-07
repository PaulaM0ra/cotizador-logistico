console.log("combustible-ui.js cargado correctamente");

document.addEventListener("DOMContentLoaded", function () {
    const campoPrecio = document.getElementById("precio-combustible");
    const selectorCombustible = document.getElementById("tipo-combustible");

    if (!campoPrecio || !selectorCombustible) {
        console.error("No se encontraron los campos de combustible.");
        return;
    }

    const contenedorPrecio = campoPrecio.closest(".col-12");

    const panelReferencia = document.createElement("div");
    panelReferencia.className = "mt-2";
    panelReferencia.innerHTML = `
        <div class="form-check form-switch">
            <input
                id="usar-precio-automatico"
                class="form-check-input"
                type="checkbox"
                checked
            >
            <label class="form-check-label" for="usar-precio-automatico">
                Usar precio sugerido por municipio
            </label>
        </div>

        <div
            id="informacion-precio-combustible"
            class="alert alert-secondary py-2 px-3 mt-2 mb-0 small"
        >
            Selecciona el municipio de origen y el combustible.
        </div>
    `;

    contenedorPrecio.appendChild(panelReferencia);

    const interruptorAutomatico = document.getElementById(
        "usar-precio-automatico"
    );
    const informacionPrecio = document.getElementById(
        "informacion-precio-combustible"
    );

    let ultimaConsulta = "";
    let controlador = null;

    function formatearDinero(valor) {
        return new Intl.NumberFormat("es-CO", {
            style: "currency",
            currency: "COP",
            maximumFractionDigits: 0
        }).format(valor);
    }

    function nombreMes(numeroMes) {
        const meses = [
            "enero", "febrero", "marzo", "abril",
            "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre"
        ];

        return meses[Number(numeroMes) - 1] || `mes ${numeroMes}`;
    }

    function obtenerMunicipioOrigen() {
        return document.getElementById("origen-municipio");
    }

    function cambiarEstado(texto, clase = "alert-secondary") {
        informacionPrecio.className = `alert ${clase} py-2 px-3 mt-2 mb-0 small`;
        informacionPrecio.textContent = texto;
    }

    async function actualizarPrecioAutomatico(forzar = false) {
        const selectorMunicipio = obtenerMunicipioOrigen();

        if (!selectorMunicipio || !selectorMunicipio.value) {
            cambiarEstado(
                "Selecciona el municipio de origen para consultar el precio."
            );
            return;
        }

        if (!interruptorAutomatico.checked) {
            campoPrecio.readOnly = false;
            cambiarEstado(
                "Precio manual activado. Verifica el valor antes de cotizar.",
                "alert-warning"
            );
            return;
        }

        const codigoMunicipio = selectorMunicipio.value;
        const producto = selectorCombustible.value;
        const claveConsulta = `${codigoMunicipio}|${producto}`;

        if (!forzar && claveConsulta === ultimaConsulta) {
            return;
        }

        ultimaConsulta = claveConsulta;
        campoPrecio.readOnly = true;
        cambiarEstado("Consultando precio de referencia...");

        if (controlador) controlador.abort();
        controlador = new AbortController();

        try {
            const parametros = new URLSearchParams({
                codigo_municipio: codigoMunicipio,
                producto: producto
            });

            const respuesta = await fetch(
                `/combustibles/precio?${parametros.toString()}`,
                { signal: controlador.signal }
            );

            const contenido = await respuesta.json();

            if (!respuesta.ok) {
                const detalle = contenido?.detail;
                const mensaje = typeof detalle === "string"
                    ? detalle
                    : detalle?.mensaje || "No se encontró un precio de referencia.";
                throw new Error(mensaje);
            }

            campoPrecio.value = Math.round(contenido.precio_promedio);

            const texto = [
                `${contenido.municipio}, ${contenido.departamento}.`,
                `Promedio: ${formatearDinero(contenido.precio_promedio)}.`,
                `Rango: ${formatearDinero(contenido.precio_minimo)} a ${formatearDinero(contenido.precio_maximo)}.`,
                `${contenido.cantidad_estaciones} estaciones.`,
                `Periodo: ${nombreMes(contenido.mes)} de ${contenido.periodo}.`,
                contenido.advertencia
            ].join(" ");

            cambiarEstado(texto, "alert-warning");
        } catch (error) {
            if (error.name === "AbortError") return;

            console.error(error);
            campoPrecio.readOnly = false;
            cambiarEstado(
                `${error.message} Puedes ingresar el precio manualmente.`,
                "alert-danger"
            );
        }
    }

    document.addEventListener("change", function (evento) {
        if (evento.target?.id === "origen-municipio") {
            ultimaConsulta = "";
            actualizarPrecioAutomatico(true);
        }
    });

    selectorCombustible.addEventListener("change", function () {
        ultimaConsulta = "";
        actualizarPrecioAutomatico(true);
    });

    interruptorAutomatico.addEventListener("change", function () {
        ultimaConsulta = "";
        actualizarPrecioAutomatico(true);
    });

    const observador = new MutationObserver(function () {
        const selectorMunicipio = obtenerMunicipioOrigen();

        if (selectorMunicipio?.value && interruptorAutomatico.checked) {
            actualizarPrecioAutomatico();
        }
    });

    const formulario = document.getElementById("form-cotizacion");
    observador.observe(formulario, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["value"]
    });

    setTimeout(function () {
        actualizarPrecioAutomatico(true);
    }, 1500);
});
