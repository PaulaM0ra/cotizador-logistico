import {
initializeApp
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
 
import {
createUserWithEmailAndPassword,
getAuth,
onAuthStateChanged,
sendEmailVerification,
sendPasswordResetEmail,
signInWithEmailAndPassword,
signOut
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";
const configuracion = window.FIREBASE_CONFIG;
const faltaConfiguracion = !configuracion || Object.values(configuracion).some(
    (valor) => String(valor).startsWith("REEMPLAZAR_")
);

const aplicacion = faltaConfiguracion ? null : initializeApp(configuracion);
const auth = aplicacion ? getAuth(aplicacion) : null;
window.firebaseAuth = auth;

const mensaje = document.getElementById("mensaje-auth");
const contenidoAcceso = document.getElementById("contenido-acceso");
const contenidoSesion = document.getElementById("contenido-sesion");
const usuarioSesion = document.getElementById("usuario-sesion");

function mostrarMensaje(texto, tipo = "danger") {
    mensaje.textContent = texto;
    mensaje.className = `alert alert-${tipo}`;
    mensaje.classList.remove("d-none");
}

function ocultarMensaje() {
    mensaje.textContent = "";
    mensaje.classList.add("d-none");
}

function traducirError(error) {
    const mensajes = {
        "auth/email-already-in-use": "El correo ya está registrado.",
        "auth/invalid-email": "El correo no es válido.",
        "auth/invalid-credential": "Correo o contraseña incorrectos.",
        "auth/missing-password": "Debes ingresar la contraseña.",
        "auth/too-many-requests": "Demasiados intentos. Intenta más tarde.",
        "auth/weak-password": "La contraseña no cumple la política configurada.",
        "auth/user-disabled": "La cuenta está desactivada.",
        "auth/network-request-failed": "No fue posible conectarse con Firebase."
    };

    return mensajes[error.code] || error.message || "Ocurrió un error de autenticación.";
}

async function enviarBackend(ruta, metodo, cuerpo) {
    const usuario = auth.currentUser;

    if (!usuario) {
        throw new Error("No hay una sesión activa.");
    }

    const token = await usuario.getIdToken(true);
    const respuesta = await fetch(ruta, {
        method: metodo,
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json"
        },
        body: cuerpo ? JSON.stringify(cuerpo) : undefined
    });

    const contenido = await respuesta.json();

    if (!respuesta.ok) {
        const detalle = contenido?.detail;
        throw new Error(
            typeof detalle === "string"
                ? detalle
                : detalle?.mensaje || "El backend rechazó la solicitud."
        );
    }

    return contenido;
}

function activarPestana(idPanel) {
    document.querySelectorAll(".panel-auth").forEach((panel) => {
        panel.classList.toggle("d-none", panel.id !== idPanel);
    });

    document.querySelectorAll("[data-panel]").forEach((boton) => {
        boton.classList.toggle("active", boton.dataset.panel === idPanel);
    });

    ocultarMensaje();
}

document.querySelectorAll("[data-panel]").forEach((boton) => {
    boton.addEventListener("click", () => activarPestana(boton.dataset.panel));
});

document.getElementById("form-registro").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    ocultarMensaje();

    const nombre = document.getElementById("registro-nombre").value.trim();
    const telefono = document.getElementById("registro-telefono").value.trim();
    const email = document.getElementById("registro-email").value.trim();
    const password = document.getElementById("registro-password").value;
    const confirmar = document.getElementById("registro-confirmar").value;

    if (password !== confirmar) {
        mostrarMensaje("Las contraseñas no coinciden.");
        return;
    }

    try {
        const credencial = await createUserWithEmailAndPassword(auth, email, password);
        await sendEmailVerification(credencial.user);
        await enviarBackend("/usuarios/perfil", "POST", {
            nombre,
            telefono: telefono || null,
            rol: "conductor"
        });
        mostrarMensaje(
            "Cuenta creada. Revisa el correo para verificar la dirección.",
            "success"
        );
    } catch (error) {
        console.error(error);
        mostrarMensaje(traducirError(error));
    }
});

document.getElementById("form-login").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    ocultarMensaje();

    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;

    try {
        await signInWithEmailAndPassword(auth, email, password);
        mostrarMensaje("Sesión iniciada correctamente.", "success");
    } catch (error) {
        console.error(error);
        mostrarMensaje(traducirError(error));
    }
});

document.getElementById("form-recuperar").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    ocultarMensaje();

    const email = document.getElementById("recuperar-email").value.trim();

    try {
        await sendPasswordResetEmail(auth, email);
        mostrarMensaje(
            "Si el correo corresponde a una cuenta habilitada, recibirás instrucciones para restablecer la contraseña.",
            "success"
        );
    } catch (error) {
        console.error(error);
        mostrarMensaje(traducirError(error));
    }
});

document.getElementById("boton-cerrar-sesion").addEventListener("click", async () => {
    try {
        await signOut(auth);
        activarPestana("panel-login");
        mostrarMensaje("Sesión cerrada.", "success");
    } catch (error) {
        mostrarMensaje(traducirError(error));
    }
});

if (faltaConfiguracion) {
    mostrarMensaje("Debes completar /js/firebase-config.js con la configuración de tu aplicación web Firebase.");
    document.querySelectorAll("button, input").forEach((elemento) => {
        elemento.disabled = true;
    });
} else {
    onAuthStateChanged(auth, async (usuario) => {
        contenidoAcceso.classList.toggle("d-none", Boolean(usuario));
        contenidoSesion.classList.toggle("d-none", !usuario);

        if (!usuario) return;

        usuarioSesion.textContent = usuario.email || usuario.uid;

        try {
            const perfil = await enviarBackend("/usuarios/me", "GET");
            document.getElementById("perfil-nombre").textContent = perfil.nombre;
            document.getElementById("perfil-rol").textContent = perfil.rol;
        } catch (error) {
            console.error(error);
            document.getElementById("perfil-nombre").textContent = "Perfil pendiente";
            document.getElementById("perfil-rol").textContent = "conductor";
        }
    });
}
