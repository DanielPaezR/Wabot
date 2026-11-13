// Suscripción a notificaciones push (profesionales y clientes). Una sola implementación.
// - La clave pública VAPID se pide al servidor (antes estaba escrita a mano en dos archivos).
// - La identidad (profesional o cliente) la determina la sesión del servidor, no lo que envíe esta página.
(function () {
    'use strict';

    function base64AUint8(base64) {
        const relleno = '='.repeat((4 - (base64.length % 4)) % 4);
        const crudo = atob((base64 + relleno).replace(/-/g, '+').replace(/_/g, '/'));
        return Uint8Array.from(crudo, c => c.charCodeAt(0));
    }

    function soportado() {
        return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    }

    async function clavePublica() {
        const r = await fetch('/api/push/public-key', { credentials: 'same-origin' });
        const j = await r.json().catch(() => ({}));
        if (!j.success || !j.publicKey) throw new Error('Las notificaciones no están configuradas en el servidor');
        return j.publicKey;
    }

    function mismaClave(suscripcion, clave) {
        const actual = suscripcion.options && suscripcion.options.applicationServerKey;
        if (!actual) return false;
        const a = new Uint8Array(actual);
        return a.length === clave.length && a.every((v, i) => v === clave[i]);
    }

    /** Devuelve la suscripción push de este dispositivo (la crea si hace falta). Lanza un Error con un mensaje legible. */
    async function obtenerSuscripcion() {
        if (!soportado()) throw new Error('Tu navegador no admite notificaciones');
        const registro = await navigator.serviceWorker.register('/service-worker.js');
        await navigator.serviceWorker.ready;

        let permiso = Notification.permission;
        if (permiso === 'default') permiso = await Notification.requestPermission();
        if (permiso !== 'granted') throw new Error('Permite las notificaciones en la configuración del sitio');

        const clave = base64AUint8(await clavePublica());
        let suscripcion = await registro.pushManager.getSubscription();
        // Si la clave del servidor cambió, la suscripción vieja ya no funciona: se reemplaza
        if (suscripcion && !mismaClave(suscripcion, clave)) {
            await suscripcion.unsubscribe();
            suscripcion = null;
        }
        return suscripcion || registro.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: clave });
    }

    async function enviarAlServidor(url, cuerpo) {
        const r = await fetch(url, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cuerpo),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.success) throw new Error(j.error || 'No se pudo guardar la suscripción');
        return j;
    }

    /** Profesional: activa los avisos en este dispositivo. */
    window.suscribirProfesional = async function () {
        const s = await obtenerSuscripcion();
        await enviarAlServidor('/api/push/subscribe', { subscription: s.toJSON() });
        return true;
    };

    /** Cliente: activa los avisos de sus citas. Devuelve {ok, error}. */
    window.suscribirCliente = async function (_telefono, negocioId) {
        try {
            const s = await obtenerSuscripcion();
            await enviarAlServidor('/api/push/subscribe-cliente', { subscription: s.toJSON(), negocio_id: negocioId });
            return { ok: true };
        } catch (e) {
            return { ok: false, error: e.message };
        }
    };

    function avisar(mensaje, tipo) {
        if (typeof window.mostrarNotificacion === 'function') window.mostrarNotificacion(mensaje, tipo);
        else alert(mensaje);
    }

    // ---- Botón "Activar avisos" del panel del profesional ----
    function iniciarBotonProfesional() {
        const boton = document.getElementById('pushButton');
        if (!boton) return;
        const poner = (texto, desactivado) => { boton.textContent = texto; boton.disabled = !!desactivado; };

        if (!soportado()) { poner('Avisos no disponibles', true); return; }

        if (Notification.permission === 'denied') {
            poner('Avisos bloqueados');
            boton.addEventListener('click', () => avisar('Para activar los avisos: abre la configuración del sitio en tu navegador, permite "Notificaciones" y recarga la página.', 'warning'));
            return;
        }

        if (Notification.permission === 'granted') {
            // Ya hay permiso: se vuelve a registrar el dispositivo en silencio para mantener sincronizado el servidor
            window.suscribirProfesional().then(() => poner('Avisos activados', true)).catch(() => poner('Activar avisos'));
        }

        boton.addEventListener('click', async () => {
            poner('Activando...', true);
            try {
                await window.suscribirProfesional();
                poner('Avisos activados', true);
                avisar('Listo: recibirás avisos de citas nuevas, canceladas y recordatorios en este dispositivo');
            } catch (e) {
                poner('Activar avisos');
                avisar(e.message, 'error');
            }
        });
    }

    window.addEventListener('load', () => setTimeout(iniciarBotonProfesional, 500));
})();
