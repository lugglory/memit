const CACHE = 'memit-v4';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
  // 구버전 캐시 전부 삭제
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // navigate 요청(HTML)은 항상 네트워크 우선 → 오프라인 시에만 캐시 폴백
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }

  // JS/CSS 등 정적 에셋은 캐시 우선 (Vite가 콘텐츠 해시로 파일명 관리)
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      });
    })
  );
});
