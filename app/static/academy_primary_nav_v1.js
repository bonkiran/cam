(() => {
  const TOP_TABS = [
    ['overview', 'Dashboard'],
    ['registration', 'Registration'],
    ['players', 'Players'],
    ['programs', 'Programs'],
    ['coaches', 'Coaches'],
    ['fees', 'Finance'],
    ['reports', 'Reports'],
    ['settings', 'Settings'],
  ];

  const TOP_FOR_ROUTE = {
    overview: 'overview',
    registration: 'registration',
    players: 'players',
    player360: 'players',
    reviews: 'players',
    attendance: 'players',
    programs: 'programs',
    batches: 'programs',
    teams: 'programs',
    tournaments: 'programs',
    coaches: 'coaches',
    fees: 'fees',
    reports: 'reports',
    settings: 'settings',
    setup: 'settings',
    access: 'settings',
    parent: 'settings',
  };

  let scheduled = false;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    const params = new URLSearchParams(query);
    return { page: page || 'dashboard', tab: params.get('tab') || 'overview' };
  }

  function go(tab) {
    location.hash = tab === 'overview' ? 'academy' : `academy?tab=${encodeURIComponent(tab)}`;
  }

  function setActive(nav, active) {
    nav.querySelectorAll('button[data-cam-primary-tab]').forEach((button) => {
      const selected = button.dataset.camPrimaryTab === active;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-current', selected ? 'page' : 'false');
    });
  }

  function build(nav, active) {
    nav.textContent = '';
    TOP_TABS.forEach(([tab, label]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'academy-primary-nav-button';
      button.dataset.camPrimaryTab = tab;
      button.textContent = label;
      button.addEventListener('click', () => {
        setActive(nav, tab);
        go(tab);
      });
      nav.appendChild(button);
    });
    nav.dataset.camPrimarySignature = TOP_TABS.map(([tab]) => tab).join('|');
    setActive(nav, active);
  }

  function takeOwnership() {
    scheduled = false;
    const info = route();
    document.body.classList.toggle('cam-academy-primary-nav-active', info.page === 'academy');
    if (info.page !== 'academy') return;

    const workspace = document.getElementById('academyWorkspace');
    if (!workspace) return;

    let nav = workspace.querySelector(':scope > .academy-primary-nav');
    const legacy = workspace.querySelector(':scope > .academy-tabs');

    if (!nav && legacy) {
      nav = legacy;
      nav.classList.remove('academy-tabs');
      nav.classList.add('academy-primary-nav');
      nav.dataset.camNavOwner = 'academy-primary-nav-v1';
      nav.setAttribute('role', 'navigation');
      nav.setAttribute('aria-label', 'Academy');
      nav.removeAttribute('data-owner-console');
      build(nav, TOP_FOR_ROUTE[info.tab] || 'overview');
    } else if (nav) {
      const expectedSignature = TOP_TABS.map(([tab]) => tab).join('|');
      if (nav.dataset.camPrimarySignature !== expectedSignature || nav.children.length !== TOP_TABS.length) {
        build(nav, TOP_FOR_ROUTE[info.tab] || 'overview');
      } else {
        setActive(nav, TOP_FOR_ROUTE[info.tab] || 'overview');
      }
    }

    // There must never be a second primary Academy tab row. A fresh legacy row
    // can only appear when the old base workspace renderer remounts. Convert it
    // on this pass; any additional direct-child legacy row is stale and removed.
    const legacyRows = [...workspace.querySelectorAll(':scope > .academy-tabs')];
    legacyRows.forEach((row) => {
      if (row !== nav) row.remove();
    });
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(takeOwnership);
  }

  // This controller is intentionally loaded immediately after academy_v3.js and
  // before feature modules. It removes the .academy-tabs hook before legacy
  // feature scripts can inject Programs, Access, Parent, Reviews or Reports tabs.
  window.CAM_ACADEMY_PRIMARY_NAV_OWNER = 'academy-primary-nav-v1';
  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  takeOwnership();
})();
