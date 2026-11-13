// service-worker.js - notificaciones push de Wabot (profesionales y clientes)
const CACHE_NAME = 'wabot-v3';
// Solo se guardan en caché los íconos; las páginas siempre se piden a la red (antes se servía '/' viejo desde la caché)
const ARCHIVOS = ['/static/icons/icon-192x192.png', '/static/icons/icon-512x512.png', '/static/icons/icon-72x72.png'];

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(ARCHIVOS)).catch(() => {}));
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then(nombres => Promise.all(nombres.filter(n => n !== CACHE_NAME).map(n => caches.delete(n))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (event.request.method === 'GET' && url.origin === self.location.origin && ARCHIVOS.includes(url.pathname)) {
        event.respondWith(caches.match(event.request).then(r => r || fetch(event.request)));
    }
    // todo lo demás va directo a la red
});

self.addEventListener('push', (event) => {
    let datos = {};
    try {
        datos = event.data ? event.data.json() : {};
    } catch (e) {
        datos = { body: event.data ? event.data.text() : '' };
    }
    const opciones = {
        body: datos.body || 'Tienes una notificación nueva',
        icon: datos.icon || '/static/icons/icon-192x192.png',
        badge: '/static/icons/icon-72x72.png',
        vibrate: [200, 100, 200],
        data: { url: datos.url || '/', citaId: datos.citaId || null },
        actions: [{ action: 'ver', title: 'Ver' }],
    };
    if (datos.tag) {          // un aviso nuevo de la misma cita reemplaza al anterior en vez de apilarse
        opciones.tag = datos.tag;
        opciones.renotify = true;
    }
    event.waitUntil(self.registration.showNotification(datos.title || 'Wabot', opciones));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    // Siempre se abre la dirección que trae el aviso: la del profesional (/profesional) o la del cliente (/cliente/<id>)
    const destino = new URL((event.notification.data && event.notification.data.url) || '/', self.location.origin);
    if (destino.origin !== self.location.origin) return;

    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((ventanas) => {
            for (const ventana of ventanas) {
                if (new URL(ventana.url).pathname === destino.pathname && 'focus' in ventana) {
                    return ventana.focus();
                }
            }
            return self.clients.openWindow(destino.href);
        })
    );
});
