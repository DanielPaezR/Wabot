// static/sw-login.js
const CACHE_NAME = 'wabot-login-v1';
const urlsToCache = [
  '/',
  '/login',
  '/static/icons/icon-login-192.png',
  '/static/icons/icon-login-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('✅ Cache abierto para login');
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request);
      })
  );
});