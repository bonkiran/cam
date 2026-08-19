(() => {
  const VERSION = '1';
  const CACHE_TTL_MS = 8000;
  const TRANSITION_TIMEOUT_MS = 12000;
  const nativeFetch = window.fetch.bind(window);
  const responseCache = new Map();
  const inFlight = new Map();
  let lastRoute = routeInfo();
  let transition = null;

  const metrics = {
    version: VERSION,
    cacheHits: 0,
    deduplicatedRequests: 0,
    networkGets: 0,
    transitionsStarted: 0,
    transitionsCompleted: 0,
  };
  window.__academyNavigationPerformance = metrics;

  function routeInfo() {
    const raw = location.hash.replace(/^#/, '') || 'dashboard';
    const [page, query = ''] = raw.split('?');
    const params = new URLSearchParams(query);
    return { page, tab: page === 'academy' ? (params.get('tab') || 'overview') : null };
  }

  function apiKey(input) {
    try {
      const value = typeof input === 'string' ? input : input?.url;
      const url = new URL(value, location.origin);
      if (url.origin !== location.origin) return null;
      const path = `${url.pathname}${url.search}`;
      if (url.pathname === '/api/dashboard' || url.pathname.startsWith('/api/academy/')) return path;
      return null;
    } catch {
      return null;
    }
  }

  function methodFor(input, init) {
    return String(init?.method || input?.method || 'GET').toUpperCase();
  }

  function rebuildResponse(entry) {
    return new Response(entry.body, {
      status: entry.status,
      statusText: entry.statusText,
      headers: entry.headers,
    });
  }

  async function captureResponse(response) {
    const body = await response.clone().text();
    return {
      body,
      status: response.status,
      statusText: response.statusText,
      headers: [...response.headers.entries()],
      storedAt: Date.now(),
    };
  }

  window.fetch = async function academyCachedFetch(input, init = {}) {
    const method = methodFor(input, init);
    const key = apiKey(input);

    if (method !== 'GET') {
      if (key || String(typeof input === 'string' ? input : input?.url || '').includes('/api/videos')) {
        responseCache.clear();
        inFlight.clear();
      }
      return nativeFetch(input, init);
    }

    if (!key) return nativeFetch(input, init);

    const cached = responseCache.get(key);
    if (cached && Date.now() - cached.storedAt < CACHE_TTL_MS) {
      metrics.cacheHits += 1;
      return rebuildResponse(cached);
    }

    if (inFlight.has(key)) {
      metrics.deduplicatedRequests += 1;
      const shared = await inFlight.get(key);
      return rebuildResponse(shared);
    }

    metrics.networkGets += 1;
    const pending = (async () => {
      const response = await nativeFetch(input, init);
      const captured = await captureResponse(response);
      if (response.ok) responseCache.set(key, captured);
      return captured;
    })();
    inFlight.set(key, pending);

    try {
      const captured = await pending;
      return rebuildResponse(captured);
    } finally {
      inFlight.delete(key);
    }
  };

  function tabForButton(button) {
    if (!button) return null;
    if (button.dataset?.academyTab) return button.dataset.academyTab;
    if (button.id === 'academyProgramsTab') return 'programs';
    const label = (button.textContent || '').trim();
    const map = {
      'Dashboard': 'overview',
      'Overview': 'overview',
      'Academy Setup': 'setup',
      'Players': 'players',
      'Programs & Enrollment': 'programs',
      'Batches & Sessions': 'batches',
      'Coaches': 'coaches',
      'Attendance': 'attendance',
      'Teams & Matches': 'teams',
      'Tournaments': 'tournaments',
      'Fees & Payments': 'fees',
    };
    return map[label] || null;
  }

  function setActiveTab(target) {
    document.querySelectorAll('#academyWorkspace .academy-tabs button').forEach((button) => {
      button.classList.toggle('active', tabForButton(button) === target);
    });
  }

  function scrubSnapshot(node) {
    if (!(node instanceof Element)) return;
    node.removeAttribute('id');
    node.removeAttribute('name');
    node.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));
    node.querySelectorAll('input, button, select, textarea, a').forEach((el) => {
      el.setAttribute('tabindex', '-1');
      el.setAttribute('aria-hidden', 'true');
      if ('disabled' in el) el.disabled = true;
    });
  }

  function removeSnapshot() {
    document.getElementById('academyTransitionSnapshot')?.remove();
    document.documentElement.classList.remove('academy-tab-transitioning');
    delete document.documentElement.dataset.academyTransitionTarget;
  }

  function createSnapshot() {
    if (document.getElementById('academyTransitionSnapshot')) return;
    const content = document.querySelector('#academyWorkspace .academy-content');
    if (!content) return;
    const rect = content.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const overlay = document.createElement('div');
    overlay.id = 'academyTransitionSnapshot';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.style.cssText = [
      'position:fixed',
      `left:${Math.max(0, rect.left)}px`,
      `top:${Math.max(0, rect.top)}px`,
      `width:${Math.max(1, rect.width)}px`,
      `height:${Math.max(1, Math.min(rect.height, window.innerHeight - Math.max(0, rect.top)))}px`,
      'overflow:hidden',
      'pointer-events:none',
      'z-index:8500',
      'background:#f7fbf9',
      'box-sizing:border-box',
    ].join(';');

    const progress = document.createElement('div');
    progress.className = 'academy-transition-progress';
    progress.style.cssText = 'position:absolute;left:0;right:0;top:0;height:3px;overflow:hidden;z-index:2;background:rgba(31,111,75,.10)';
    progress.innerHTML = '<span style="display:block;height:100%;width:38%;background:#2f855a;animation:academyTransitionSlide .9s ease-in-out infinite alternate"></span>';
    overlay.appendChild(progress);

    const clone = content.cloneNode(true);
    scrubSnapshot(clone);
    clone.style.pointerEvents = 'none';
    clone.style.margin = '0';
    overlay.appendChild(clone);
    document.body.appendChild(overlay);
  }

  function targetReady(tab) {
    const content = document.querySelector('#academyWorkspace .academy-content');
    if (!content || content.querySelector('.academy-loading')) return false;
    switch (tab) {
      case 'overview': return !!content.querySelector('.academy-hero');
      case 'setup': return !!content.querySelector('#academyProfileForm');
      case 'players': return !!content.querySelector('.academy-player-panel');
      case 'programs': return !!content.querySelector('#openProgramForm');
      case 'coaches': return !!content.querySelector('#openCoachForm');
      case 'batches': return !!content.querySelector('#openBatchForm');
      case 'attendance': {
        const selector = content.querySelector('#attendanceSessionSelect');
        const session = content.querySelector('#attendanceSessionWorkspace');
        return !!selector && !!session && !session.querySelector('.academy-loading');
      }
      case 'teams': return !!content.querySelector('#openTeamForm') || !!content.querySelector('.academy-foundation-card');
      case 'tournaments': return !!content.querySelector('#openTournamentForm') || !!content.querySelector('.academy-foundation-card');
      case 'fees': return !!content.querySelector('#openFeePlan') || !!content.querySelector('.academy-foundation-card');
      default: return content.children.length > 0;
    }
  }

  function finishTransitionIfReady() {
    if (!transition) return;
    const current = routeInfo();
    if (current.page !== 'academy') {
      transition = null;
      removeSnapshot();
      return;
    }
    if (current.tab !== transition.target || !targetReady(transition.target)) return;

    const completed = transition;
    transition = null;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (routeInfo().page === 'academy' && routeInfo().tab === completed.target) {
        removeSnapshot();
        metrics.transitionsCompleted += 1;
      }
    }));
  }

  function beginTransition(target) {
    const current = routeInfo();
    if (current.page !== 'academy' || !target || current.tab === target) return;

    setActiveTab(target);
    // Owner Console and legacy Academy click handlers can both update tab classes in the
    // same click task. Re-assert the intended target in a microtask so the first rendered
    // frame always reflects the tab the user actually selected.
    queueMicrotask(() => {
      if (transition?.target === target) setActiveTab(target);
    });
    if (!transition) createSnapshot();
    transition = { target, startedAt: performance.now() };
    metrics.transitionsStarted += 1;
    document.documentElement.classList.add('academy-tab-transitioning');
    document.documentElement.dataset.academyTransitionTarget = target;

    window.setTimeout(() => {
      if (!transition || transition.target !== target) return;
      transition = null;
      removeSnapshot();
    }, TRANSITION_TIMEOUT_MS);
  }

  const style = document.createElement('style');
  style.id = 'academyNavigationPerformanceStyle';
  style.textContent = `
    @keyframes academyTransitionSlide {
      from { transform: translateX(-15%); opacity: .45; }
      to { transform: translateX(180%); opacity: 1; }
    }
    html.academy-tab-transitioning #academyWorkspace .academy-tabs button.active {
      position: relative;
    }
  `;
  document.head.appendChild(style);

  document.addEventListener('click', (event) => {
    const button = event.target.closest('#academyWorkspace .academy-tabs button, [data-academy-tab]');
    if (!button) return;
    const target = tabForButton(button);
    beginTransition(target);
  }, true);

  window.addEventListener('hashchange', () => {
    const current = routeInfo();
    if (lastRoute.page === 'academy' && current.page === 'academy' && lastRoute.tab !== current.tab) {
      if (!transition) beginTransition(current.tab);
      setActiveTab(current.tab);
    } else if (current.page !== 'academy') {
      transition = null;
      removeSnapshot();
    }
    lastRoute = current;
    queueMicrotask(finishTransitionIfReady);
  }, true);

  const observer = new MutationObserver(() => {
    finishTransitionIfReady();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  window.addEventListener('resize', () => {
    if (!transition) return;
    removeSnapshot();
    createSnapshot();
  });
})();
