(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  let scheduled = false;

  function dashboardActive() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    const tab = new URLSearchParams(query).get('tab') || 'overview';
    return (page || 'dashboard') === 'cam' && tab === 'overview';
  }

  function legacyRegistrationPanel(content) {
    const title = $$('h1,h2,h3,h4,strong,b,span,div', content).find(node => {
      if (node.children.length) return false;
      const text = (node.textContent || '').trim();
      return text === 'New Player Registrations' || text.startsWith('New Player Registrations:');
    });
    return title?.closest('article,.panel,section') || null;
  }

  function dedupe() {
    scheduled = false;
    if (!dashboardActive()) return;
    const content = $('#camWorkspace .cam-content');
    if (!content) return;

    const enrollmentPanels = $$('.cam-new-player-enrollments', content);
    if (!enrollmentPanels.length) return;

    const keep = enrollmentPanels.find(panel => panel.closest('.cam-dashboard-v2-grid')) || enrollmentPanels[0];
    enrollmentPanels.forEach(panel => {
      if (panel !== keep) panel.remove();
    });

    const legacy = legacyRegistrationPanel(content);
    if (legacy && legacy !== keep) legacy.remove();
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(dedupe);
  }

  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(() => {
    if (dashboardActive()) schedule();
  }).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
