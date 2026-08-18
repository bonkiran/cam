(() => {
  // app.js owns the generic application router. Academy is now a real module,
  // so the base router must not render its legacy placeholder for #academy.
  if (typeof window.router !== 'function' || typeof window.route !== 'function') {
    console.warn('Academy router bridge could not find the base router.');
    return;
  }

  const baseRouter = window.router;
  window.removeEventListener('hashchange', baseRouter);

  function clearLegacyAcademyContent() {
    if (window.route().page !== 'academy') return;
    const main = document.querySelector('#app .main');
    if (!main) return;
    [...main.children].forEach((child) => {
      if (!child.classList.contains('topbar')) child.remove();
    });
  }

  function routedHashChange() {
    const current = window.route();
    if (current.page === 'academy') {
      clearLegacyAcademyContent();
      window.__academyBaseRouterBypassed = true;
      return;
    }
    baseRouter();
  }

  window.addEventListener('hashchange', routedHashChange);
  window.__academyBaseRouterBypassed = true;

  // app.js calls router() once during initial script evaluation. If the browser
  // was opened directly on #academy, remove that legacy placeholder immediately
  // in the same synchronous script turn, before the browser can paint it.
  clearLegacyAcademyContent();
})();
