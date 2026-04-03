// Orallexa Capital — Service Worker
// Cache-first for static assets, network-first for pages, offline fallback

const CACHE_VERSION = "orallexa-v2";
const STATIC_CACHE = "orallexa-static-v2";
const RUNTIME_CACHE = "orallexa-runtime-v2";

// App shell — precached on install
const PRECACHE_URLS = [
  "/",
  "/offline",
  "/manifest.json",
  "/logo.svg",
  "/pixel_bull.png",
  "/icon-192.png",
  "/icon-512.png",
  "/favicon.ico",
];

// --------------- Install ---------------
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

// --------------- Activate ---------------
self.addEventListener("activate", (event) => {
  const keepCaches = new Set([STATIC_CACHE, RUNTIME_CACHE]);
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => !keepCaches.has(k)).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// --------------- Fetch ---------------
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET, cross-origin, chrome-extension, websocket
  if (request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;

  // API calls — network-first, no cache fallback (data must be fresh)
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) {
    event.respondWith(networkFirst(request, RUNTIME_CACHE));
    return;
  }

  // Static assets (JS, CSS, fonts, images) — cache-first
  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Navigation (HTML pages) — network-first with offline fallback
  if (request.mode === "navigate") {
    event.respondWith(networkFirstWithOfflineFallback(request));
    return;
  }

  // Everything else — network-first
  event.respondWith(networkFirst(request, RUNTIME_CACHE));
});

// --------------- Strategies ---------------

function cacheFirst(request, cacheName) {
  return caches.match(request).then((cached) => {
    if (cached) return cached;
    return fetch(request).then((response) => {
      if (response.ok) {
        const clone = response.clone();
        caches.open(cacheName).then((cache) => cache.put(request, clone));
      }
      return response;
    });
  });
}

function networkFirst(request, cacheName) {
  return fetch(request)
    .then((response) => {
      if (response.ok) {
        const clone = response.clone();
        caches.open(cacheName).then((cache) => cache.put(request, clone));
      }
      return response;
    })
    .catch(() => caches.match(request));
}

function networkFirstWithOfflineFallback(request) {
  return fetch(request)
    .then((response) => {
      if (response.ok) {
        const clone = response.clone();
        caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, clone));
      }
      return response;
    })
    .catch(() =>
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return caches.match("/offline");
      })
    );
}

// --------------- Push Notifications ---------------
self.addEventListener("push", (event) => {
  let data = { title: "Orallexa Capital", body: "New trading signal" };
  if (event.data) {
    try {
      data = event.data.json();
    } catch {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: "/logo.svg",
    badge: "/icon-192.png",
    tag: data.tag || "orallexa-signal",
    renotify: true,
    data: { url: data.url || "/" },
  };

  event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      // Focus existing window if one is open
      for (const client of clients) {
        if (new URL(client.url).origin === self.location.origin && "focus" in client) {
          return client.focus();
        }
      }
      // Otherwise open a new window
      return self.clients.openWindow(targetUrl);
    })
  );
});

// --------------- Helpers ---------------

function isStaticAsset(pathname) {
  return /\.(?:js|css|woff2?|ttf|otf|eot|png|jpe?g|gif|svg|ico|webp|avif)$/.test(pathname)
    || pathname.startsWith("/_next/static/");
}
