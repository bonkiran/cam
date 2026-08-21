(() => {
  const CLASS_NAME = 'academy-route-pending';
  const STYLE_ID = 'academyRouteGuardStyle';
  const VERSION = '4';

  function routeInfo() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    return {page, tab: new URLSearchParams(query).get('tab') || 'overview'};
  }

  function isAcademyRoute() {
    return routeInfo().page === 'academy';
  }

  function isAcademyOverviewRoute() {
    const r = routeInfo();
    return r.page === 'academy' && r.tab === 'overview';
  }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) {
      document.documentElement.dataset.academyRouteGuard = VERSION;
      return;
    }
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      html.${CLASS_NAME} #app .main > :not(.topbar) {
        visibility: hidden !important;
      }
      html.${CLASS_NAME} #app .main {
        position: relative;
        min-height: 280px;
      }
      html.${CLASS_NAME} #app .main::after {
        content: 'Loading Academy…';
        position: absolute;
        left: 32px;
        right: 32px;
        top: 96px;
        min-height: 110px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px solid rgba(31, 111, 75, 0.18);
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.96);
        color: #315b49;
        font-weight: 700;
        z-index: 9999;
      }
      html.${CLASS_NAME} #academyWorkspace {
        visibility: hidden !important;
      }
    `;
    document.head.appendChild(style);
    document.documentElement.dataset.academyRouteGuard = VERSION;
  }

  function setPending() {
    // The C17 Dashboard overview has its own prototype-shaped first-paint shell.
    // Do not show the old generic "Loading Academy…" card on that route.
    if (isAcademyOverviewRoute()) {
      clearPending();
      return;
    }
    ensureStyle();
    document.documentElement.classList.add(CLASS_NAME);
  }

  function clearPending() {
    document.documentElement.classList.remove(CLASS_NAME);
  }

  function releaseWhenAcademyMounted() {
    if (!isAcademyRoute() || isAcademyOverviewRoute()) {
      clearPending();
      return;
    }
    if (!document.documentElement.classList.contains(CLASS_NAME)) return;
    const workspace = document.getElementById('academyWorkspace');
    const content = workspace && workspace.querySelector('.academy-content');
    if (workspace && content) {
      requestAnimationFrame(() => {
        if (isAcademyRoute() && !isAcademyOverviewRoute() && document.getElementById('academyWorkspace')) {
          clearPending();
        }
      });
    }
  }

  // The full-page generic loading guard is retained for direct entry to non-overview
  // Academy tabs. The C17 overview uses academy_dashboard_first_paint_v1 instead.
  let wasAcademyRoute = isAcademyRoute();
  window.addEventListener('hashchange', () => {
    const nowAcademyRoute = isAcademyRoute();
    if (isAcademyOverviewRoute()) {
      clearPending();
    } else if (nowAcademyRoute && !wasAcademyRoute) {
      setPending();
    } else if (!nowAcademyRoute) {
      clearPending();
    } else {
      releaseWhenAcademyMounted();
    }
    wasAcademyRoute = nowAcademyRoute;
    queueMicrotask(releaseWhenAcademyMounted);
  });

  const observer = new MutationObserver(() => {
    releaseWhenAcademyMounted();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  ensureStyle();
  if (wasAcademyRoute && !isAcademyOverviewRoute()) setPending();
  else clearPending();
  document.addEventListener('DOMContentLoaded', releaseWhenAcademyMounted);
})();
