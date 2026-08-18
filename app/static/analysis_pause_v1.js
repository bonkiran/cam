(() => {
  const PAUSED = true;
  const ANALYSIS_ROUTES = new Set(['dashboard', 'upload', 'analyses', 'analysis', 'comparisons']);
  const BLOCKED_API_PREFIXES = ['/api/videos', '/api/biomechanics', '/api/events'];

  window.CAM_ANALYSIS_PAUSED = PAUSED;

  function currentPage() {
    const raw = location.hash.replace(/^#/, '') || 'dashboard';
    return raw.split('?')[0] || 'dashboard';
  }

  function isBlockedPath(value) {
    try {
      const url = new URL(typeof value === 'string' ? value : value.url, location.origin);
      const path = url.pathname;
      return BLOCKED_API_PREFIXES.some(prefix => path === prefix || path.startsWith(`${prefix}/`));
    } catch (_) {
      return false;
    }
  }

  // Safety belt: while Analysis is parked, do not allow browser code to send
  // video/biomechanics/event requests to the server at all. Return a local
  // response instead so accidental legacy callers cannot create Render log noise.
  // Shared Academy dependencies such as /api/dashboard remain available.
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    if (PAUSED && isBlockedPath(input)) {
      return Promise.resolve(new Response(
        JSON.stringify({ detail: 'Analysis is temporarily paused while Academy pilot work is active.' }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ));
    }
    return nativeFetch(input, init);
  };

  function guardRoute() {
    if (!PAUSED || !ANALYSIS_ROUTES.has(currentPage())) return;
    // Use replaceState so stale #analysis?id=... bookmarks are neutralized before
    // app.js handles the same hashchange event and attempts /api/videos/... calls.
    history.replaceState(null, '', `${location.pathname}${location.search}#academy`);
  }

  function markAnalysisPaused() {
    if (!PAUSED) return;
    document.querySelectorAll('[data-workspace-nav="analysis"], .sidebar .nav > button[data-route="dashboard"]').forEach(button => {
      button.disabled = true;
      button.setAttribute('aria-disabled', 'true');
      button.title = 'Analysis is temporarily paused while Academy pilot work is active.';
      button.style.opacity = '0.55';
      button.style.cursor = 'not-allowed';
    });
    document.getElementById('analysisWorkspaceTabs')?.remove();
  }

  // This file is loaded before app.js, so it protects both the initial route and
  // every later hash navigation before the legacy Analysis router sees it.
  guardRoute();
  window.addEventListener('hashchange', guardRoute);

  const observer = new MutationObserver(markAnalysisPaused);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', markAnalysisPaused);
  markAnalysisPaused();
})();
