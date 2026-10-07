/* Agrega automáticamente el token Firebase a solicitudes del mismo origen. */
(function () {
    const fetchOriginal = window.fetch.bind(window);

    function esMismoOrigen(recurso) {
        try {
            const url = new URL(
                typeof recurso === "string" ? recurso : recurso.url,
                window.location.origin
            );
            return url.origin === window.location.origin;
        } catch {
            return false;
        }
    }

    window.fetch = async function (recurso, opciones = {}) {
        const nuevasOpciones = { ...opciones };
        const headers = new Headers(
            opciones.headers ||
            (recurso instanceof Request ? recurso.headers : undefined)
        );

        const usuario = window.firebaseAuth?.currentUser;

        if (usuario && esMismoOrigen(recurso)) {
            try {
                const token = await usuario.getIdToken();
                headers.set("Authorization", `Bearer ${token}`);
            } catch (error) {
                console.error("No fue posible obtener el token Firebase.", error);
            }
        }

        nuevasOpciones.headers = headers;
        return fetchOriginal(recurso, nuevasOpciones);
    };
})();
