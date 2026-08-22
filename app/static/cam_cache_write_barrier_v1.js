(() => {
  const previousFetch = window.fetch.bind(window);
  let writeEpoch = 0;

  function requestInfo(input, init = {}) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      const url = new URL(raw, window.location.href);
      const method = String(init.method || input?.method || 'GET').toUpperCase();
      return { url, method };
    } catch {
      return null;
    }
  }

  window.fetch = function camWriteBarrierFetch(input, init = {}) {
    const info = requestInfo(input, init);
    if (!info || info.url.origin !== window.location.origin || !info.url.pathname.startsWith('/api/cam/')) {
      return previousFetch(input, init);
    }

    if (info.method !== 'GET') {
      // Increment before the write is sent. Any GET that was already in flight may
      // still finish afterward, but it belongs to the previous epoch and cannot be
      // reused by the post-write refresh below.
      writeEpoch += 1;
      return previousFetch(input, init);
    }

    if (writeEpoch === 0) return previousFetch(input, init);

    // The navigation cache keys include the query string. A write-epoch query
    // creates a fresh cache namespace after every mutation without disabling the
    // short-lived navigation cache during normal read-only navigation.
    const freshUrl = new URL(info.url.toString());
    freshUrl.searchParams.set('_cam_write_epoch', String(writeEpoch));
    return previousFetch(freshUrl.toString(), init);
  };
})();
