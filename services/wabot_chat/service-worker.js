// service-worker.js - VERSIÓN CON NOTIFICACIONES PUSH
const CACHE_NAME = 'wabot-v2';

self.addEventListener('install', (event) => {
    console.log('✅ Service Worker instalado');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                return cache.addAll([
                    '/',
                    '/manifest.json',
                    '/static/icons/icon-192x192.png',
                    '/static/icons/icon-512x512.png'
                ]);
            })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    console.log('✅ Service Worker activado');
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                return response || fetch(event.request);
            })
    );
});

// 🔥 NUEVO: MANEJADOR DE NOTIFICACIONES PUSH
self.addEventListener('push', function(event) {
    console.log('🔔 Evento push recibido');
    
    try {
        let data = {};
        if (event.data) {
            data = event.data.json();
        }
        
        const options = {
            body: data.body || 'Nueva notificación',
            icon: '/static/icons/icon-192x192.png',
            badge: '/static/icons/icon-72x72.png',
            vibrate: [200, 100, 200],
            data: {
                url: data.url || '/profesional',
                citaId: data.citaId,
                timestamp: new Date().toISOString()
            },
            actions: [
                {
                    action: 'ver',
                    title: '👁️ Ver',
                    icon: '/static/icons/eye-64.png'
                },
                {
                    action: 'cerrar',
                    title: '❌ Cerrar'
                }
            ]
        };
        
        event.waitUntil(
            self.registration.showNotification(
                data.title || '📅 Nueva Cita',
                options
            )
        );
        
    } catch (error) {
        console.error('Error en push event:', error);
    }
});

// 🔥 NUEVO: CUANDO SE HACE CLICK EN LA NOTIFICACIÓN
self.addEventListener('notificationclick', function(event) {
    console.log('🔔 Notificación clickeada:', event.notification.data);
    
    event.notification.close();
    
    const urlToOpen = event.notification.data.url || '/profesional';
    
    if (event.action === 'ver' && event.notification.data.citaId) {
        // Abrir la cita específica
        clients.openWindow(`/profesional?cita=${event.notification.data.citaId}`);
    } else if (event.action === 'cerrar') {
        // Solo cerrar
        console.log('Notificación cerrada');
    } else {
        // Click en el cuerpo de la notificación
        clients.openWindow(urlToOpen);
    }
});