(() => {
  const CLASS_NAME = 'academy-route-pending';
  const STYLE_ID = 'academyRouteGuardStyle';

  function isAcademyRoute() {
    return location.hash.replace(/^#/, '').split('?')[0] === 'academy';
  }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      html.${CLASS_NAME} #app .main > .page-head,
      html.${CLASS_NAME} #app .main > .panel {
        visibility: hidden !important;
      }
      html.${CLASS_NAME} #app .main {
        position: relative;
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
        background: rgba(255, 255, 255, 0.92);
        color: #315b49;
        font-weight: 700;
        z-index: 2;
      }
      html.${CLASS_NAME} #academyWorkspace {
        visibility: hidden !important;
      }
    `;
    document.head.appendChild(style);
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
    if (workspace && workspace.querySelector('.academy-content')) {
      requestAnimationFrame(() => {
        if (isAcademyRoute()) document.documentElement.classList.remove(CLASS_NAME);
      });
    }
  }

  // This listener is registered before app.js, so the generic router's Academy
  // placeholder is hidden before the browser has a chance to paint it.
  window.addEventListener('hashchange', () => {
    markPending();
    queueMicrotask(releaseWhenAcademyMounted);
  });

  const observer = new MutationObserver(releaseWhenAcademyMounted);
  observer.observe(document.documentElement, { childList: true, subtree: true });

  markPending();
  document.addEventListener('DOMContentLoaded', () => {
    markPending();
    releaseWhenAcademyMounted();
  });
})();
