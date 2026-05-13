// Service Worker — MentoTrack Admin PWA
// Cache assets estáticos, NUNCA cachear llamadas a /api/

const CACHE_NAME = 'mt-admin-v1';

// Assets que queremos pre-cachear en install
const PRECACHE_ASSETS = [
  '/favicon.svg',
  '/pwa-admin-192.png',
  '/pwa-admin-512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.9/babel.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/tailwindcss/2.2.19/tailwind.min.css',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap'
];

// Rutas que NUNCA deben cachearse (API, auth, datos dinámicos)
function isApiOrDynamic(url) {
  const path = new URL(url).pathname;
  return (
    path.startsWith('/api/') ||
    path === '/dashboard' ||          // El HTML siempre fresco (requiere auth cookie)
    path.startsWith('/manifest')
  );
}

// Install: pre-cachear assets estáticos
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activate: limpiar caches antiguas
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: cache-first para assets, network-only para API/dashboard
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Nunca cachear POST ni llamadas a API/dashboard
  if (request.method !== 'GET' || isApiOrDynamic(request.url)) {
    return; // Deja que el navegador lo maneje normalmente (network)
  }

  // Para assets estáticos: cache-first, fallback a network
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(request).then((networkResponse) => {
        // Solo cachear respuestas exitosas
        if (networkResponse && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseClone);
          });
        }
        return networkResponse;
      });
    })
  );
});
