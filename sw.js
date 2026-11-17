const CACHE_NAME = "golf-weather-v32-2-pwa-v2";

const APP_SHELL = [
  "./v32.2-preview.html",
  "./offline.html",
  "./manifest.json",
  "./pwa/pwa-install.js",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png",
  "./icons/icon-maskable-512.png"
];

// Install: cache the complete app shell.
// If a required local file is missing, installation fails visibly
// instead of silently creating an incomplete offline app.
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

// Activate: remove only older Golf Weather V32.2 PWA caches.
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key =>
            key.startsWith("golf-weather-v32-2-pwa-") &&
            key !== CACHE_NAME
          )
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;

  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Never intercept external requests, including weather APIs.
  if (url.origin !== self.location.origin) return;

  // Navigation: network-first, then cached V32.2, then offline page.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const copy = response.clone();
            event.waitUntil(
              caches.open(CACHE_NAME).then(cache =>
                cache.put("./v32.2-preview.html", copy)
              )
            );
          }
          return response;
        })
        .catch(async () => {
          const cachedPage = await caches.match("./v32.2-preview.html");
          if (cachedPage) return cachedPage;

          const offlinePage = await caches.match("./offline.html");
          if (offlinePage) return offlinePage;

          return new Response(
            "目前無網路連線，請連線後重新開啟 Golf Weather V32.2。",
            {
              status: 503,
              headers: { "Content-Type": "text/plain; charset=utf-8" }
            }
          );
        })
    );
    return;
  }

  // Cache-first only for local static assets.
  // Deliberately exclude JSON and all dynamic weather data.
  if (/\.(png|jpg|jpeg|svg|webp|woff2?|js|css)$/i.test(url.pathname)) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;

        return fetch(request).then(response => {
          if (response.ok) {
            const copy = response.clone();
            event.waitUntil(
              caches.open(CACHE_NAME).then(cache =>
                cache.put(request, copy)
              )
            );
          }
          return response;
        });
      })
    );
  }
});
