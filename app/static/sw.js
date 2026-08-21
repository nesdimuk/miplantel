const CACHE = "miplantel-v1";
const STATIC = [
  "/static/form.css",
  "/static/form.js",
  "/static/informe.css",
  "/static/manifest.json",
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const { request } = e;
  const url = new URL(request.url);

  // API y páginas dinámicas → network first, sin cache
  if (url.pathname.startsWith("/api/") || request.method !== "GET") return;

  // Estáticos → cache first
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(resp => {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(request, clone));
        return resp;
      }))
    );
    return;
  }

  // Páginas → network first, cache fallback
  e.respondWith(
    fetch(request).then(resp => {
      const clone = resp.clone();
      caches.open(CACHE).then(c => c.put(request, clone));
      return resp;
    }).catch(() => caches.match(request))
  );
});
