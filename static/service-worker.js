// service-worker.js - Básico
const CACHE_NAME = 'wabot-v1';

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
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                return response || fetch(event.request);
            })
    );
});