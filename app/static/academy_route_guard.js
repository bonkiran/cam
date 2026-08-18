(() => {
  const CLASS_NAME = 'academy-route-pending';
  const STYLE_ID = 'academyRouteGuardStyle';
  const VERSION = '2';

  function isAcademyRoute() {
    return location.hash.replace(/^#/, '').split('?')[0] === 'academy';
  }

  function ensureStyle() {
    let style = document.getElementById(STYLE_ID);
    if (!style) {
      style = document.createElement('style');
      style.id = STYLE_ID;
      document.head.appendChild(style);
    }
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

  // Loaded before app.js. Mark Academy routes pending synchronously so any
  // generic shell produced by the base router stays hidden regardless of how
  // later theme/navigation scripts wrap or rename the shell content.
  window.addEventListener('hashchange', () => {
    markPending();
    queueMicrotask(releaseWhenAcademyMounted);
  });

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
