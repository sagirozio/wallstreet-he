/* וולסטריטר service worker.
   Pages and data: network first (always fresh when online), cached copy only when offline or very slow.
   Icons and fonts: cache first. Third-party widgets (TradingView) are never touched. */
const V = 'ws-v1';
const SHELL = ['./', 'index.html', 'logo.svg', 'manifest.webmanifest', 'icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

function key(req) { const u = new URL(req.url); return u.origin + u.pathname; }   // ignore ?t= cache-busters

async function networkFirst(req) {
  const c = await caches.open(V);
  try {
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 8000);
    const res = await fetch(req, { signal: ctl.signal }); clearTimeout(t);
    if (res.ok) c.put(key(req), res.clone());
    return res;
  } catch (err) {
    const hit = await c.match(key(req)) || (req.mode === 'navigate' ? await c.match(new URL('./', self.registration.scope).href) : null);
    if (hit) return hit;
    throw err;
  }
}
async function cacheFirst(req) {
  const c = await caches.open(V), hit = await c.match(req.url);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === 'opaque') c.put(req.url, res.clone());
  return res;
}

self.addEventListener('fetch', e => {
  const req = e.request; if (req.method !== 'GET') return;
  const u = new URL(req.url);
  if (u.origin === location.origin) {
    if (/\.(png|svg|webmanifest)$/.test(u.pathname)) e.respondWith(cacheFirst(req));
    else e.respondWith(networkFirst(req));
  } else if (/fonts\.(googleapis|gstatic)\.com$/.test(u.hostname)) {
    e.respondWith(cacheFirst(req));
  }
});
