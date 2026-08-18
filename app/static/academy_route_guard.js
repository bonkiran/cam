(() => {
  const CLASS_NAME = 'academy-route-pending';
  const STYLE_ID = 'academyRouteGuardStyle';
  const VERSION = '2';

  function isAcademyRoute() {
    return location.hash.replace(/^#/, '').split('?')[0] === 'academy';
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

  function markPending() {
    if (!isAcademyRoute()) {
      document.documentElement.classList.remove(CLASS_NAME);
      return;
    }
    ensureStyle();
    document.documentElement.classList.add(CLASS_NAME);
  }

  function releaseWhenAcademyMounted() {
    if (!isAcademyRoute()) {
      document.documentElement.classList.remove(CLASS_NAME);
      return;
    }
    const workspace = document.getElementById('academyWorkspace');
    const content = workspace && workspace.querySelector('.academy-content');
    if (workspace && content) {
      requestAnimationFrame(() => {
        if (isAcademyRoute() && document.getElementById('academyWorkspace')) {
          document.documentElement.classList.remove(CLASS_NAME);
        }
      });
    }
  }

  window.addEventListener('hashchange', () => {
    markPending();
    queueMicrotask(releaseWhenAcademyMounted);
  });

  // Important: callbacks only toggle classes / inspect DOM. ensureStyle() is
  // idempotent and never rewrites the style node after creation, preventing the
  // observer from triggering itself in a mutation loop.
  const observer = new MutationObserver(() => {
    if (isAcademyRoute()) markPending();
    releaseWhenAcademyMounted();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  ensureStyle();
  markPending();
  document.addEventListener('DOMContentLoaded', () => {
    markPending();
    releaseWhenAcademyMounted();
  });
})();
