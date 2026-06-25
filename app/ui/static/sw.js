const CACHE_NAME = "stock-translator-shell-v3";
const APP_SHELL = [
  "/",
  "/manifest.webmanifest",
  "/static/app.css",
  "/static/app.js",
  "/static/chart_tour.js",
  "/static/assets/app-icon-192.png",
  "/static/assets/app-icon-512.png",
  "/static/assets/company-placeholder.png",
  "/static/assets/stock-dashboard-hero.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => {
        const oldShellExists = keys.some((key) => key.startsWith("stock-translator-shell-") && key !== CACHE_NAME);
        return Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
          .then(() => self.clients.claim())
          .then(() => {
            if (!oldShellExists) return undefined;
            return reloadControlledClients();
          });
      })
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (
    request.mode === "navigate"
    || url.pathname === "/"
    || APP_SHELL.includes(url.pathname)
    || url.pathname.endsWith(".js")
    || url.pathname.endsWith(".css")
  ) {
    event.respondWith(networkFirst(request));
    return;
  }

  event.respondWith(cacheFirst(request));
});

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response && response.status === 200) {
      const copy = response.clone();
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, copy);
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw error;
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.status === 200) {
    const copy = response.clone();
    const cache = await caches.open(CACHE_NAME);
    await cache.put(request, copy);
  }
  return response;
}

async function reloadControlledClients() {
  const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  return Promise.all(
    windows.map((client) => {
      if (!client.url || !client.url.startsWith(self.location.origin)) return undefined;
      return client.navigate(client.url);
    })
  );
}
