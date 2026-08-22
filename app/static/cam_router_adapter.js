(() => {
  const VERSION = '1';

  function currentPage() {
    const raw = location.hash.replace(/^#/, '') || 'dashboard';
    return raw.split('?')[0];
  }

  function preserveAcademyShell() {
    const app = document.getElementById('app');
    if (!app) return;

    let main = app.querySelector('.main');
    if (!main && typeof window.shell === 'function') {
      app.innerHTML = window.shell('', 'cam');
      if (typeof window.wireShell === 'function') window.wireShell('cam');
      main = app.querySelector('.main');
    }
    if (!main) return;

    // Keep the persistent topbar and, when already inside Academy, keep the
    // existing workspace mounted while the requested tab refreshes. Remove only
    // unrelated content left by the previous top-level route or the legacy
    // generic placeholder.
    [...main.children].forEach((child) => {
      if (child.classList.contains('topbar')) return;
      if (child.id === 'camWorkspace') return;
      child.remove();
    });
  }

  const originalRenderPlaceholder = window.renderPlaceholder;
  if (typeof originalRenderPlaceholder !== 'function') {
    console.warn('Academy router adapter could not find renderPlaceholder().');
    return;
  }

  window.renderPlaceholder = function renderPlaceholderWithAcademySupport(page) {
    if (page === 'cam') {
      preserveAcademyShell();
      return;
    }
    return originalRenderPlaceholder(page);
  };

  // app.js invokes router() once before this adapter loads. On a direct Academy
  // URL it may already have painted the legacy placeholder; remove that content
  // synchronously before the browser gets a chance to paint the page.
  if (currentPage() === 'cam') preserveAcademyShell();

  document.documentElement.dataset.camRouterAdapter = VERSION;
})();
