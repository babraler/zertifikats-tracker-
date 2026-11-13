// Service Worker: zuerst Netz (neuester Stand), ohne Netz oder nach 4 s der zuletzt geladene Stand.
// Neue Fassung = CACHE hochzählen. Alle Repos auf <name>.github.io teilen eine Origin,
// deshalb nur eigene Caches (Präfix) aufräumen.
const PRAEFIX = 'discount-tracker-';
const CACHE = PRAEFIX + 'v3';
const NETZ_TIMEOUT_MS = 4000;
const HUELLE = ['./', 'index.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(HUELLE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith(PRAEFIX) && k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

function ausCache(req) {
  return caches.match(req, {ignoreSearch: true})
    .then(r => r || (req.mode === 'navigate' ? caches.match('index.html') : undefined));
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  const ctrl = new AbortController();
  const uhr = setTimeout(() => ctrl.abort(), NETZ_TIMEOUT_MS);
  e.respondWith(
    fetch(req, {cache: 'no-cache', signal: ctrl.signal})
      .then(res => {
        clearTimeout(uhr);
        if (res.status === 200) {
          const kopie = res.clone();
          const url = new URL(req.url); url.search = '';
          e.waitUntil(caches.open(CACHE).then(c => c.put(url.href, kopie)).catch(() => {}));
        }
        return res;
      })
      .catch(() => { clearTimeout(uhr); return ausCache(req).then(r => r || Response.error()); })
  );
});
