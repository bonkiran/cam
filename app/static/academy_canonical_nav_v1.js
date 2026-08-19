(() => {
  const TOP_TABS = [
    ['overview', 'Dashboard'],
    ['players', 'Players'],
    ['programs', 'Programs'],
    ['coaches', 'Coaches'],
    ['fees', 'Finance'],
    ['reports', 'Reports'],
    ['settings', 'Settings'],
  ];

  const TOP_FOR_ROUTE = {
    overview: 'overview',
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
  let mutating = false;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    const params = new URLSearchParams(query);
    return { page: page || 'dashboard', tab: params.get('tab') || 'overview' };
  }

  function go(tab) {
    location.hash = tab === 'overview' ? 'academy' : `academy?tab=${encodeURIComponent(tab)}`;
  }

  function canonicalize() {
    scheduled = false;
    if (mutating) return;

    const info = route();
    const isAcademy = info.page === 'academy';
    document.body.classList.toggle('cam-canonical-academy', isAcademy);
    if (!isAcademy) return;

    const tabs = document.querySelector('#academyWorkspace .academy-tabs');
    if (!tabs) return;

    mutating = true;
    try {
      [...tabs.querySelectorAll('button:not([data-owner-console-tab])')].forEach(button => button.remove());

      const activeTop = TOP_FOR_ROUTE[info.tab] || 'overview';
      TOP_TABS.forEach(([tab, label]) => {
        let button = tabs.querySelector(`[data-owner-console-tab="${tab}"]`);
        if (!button) {
          button = document.createElement('button');
          button.type = 'button';
          button.className = 'academy-owner-console-tab';
          button.dataset.ownerConsoleTab = tab;
          button.dataset.academyTab = tab;
          button.addEventListener('click', event => {
            event.preventDefault();
            event.stopImmediatePropagation();
            go(tab);
          });
        }
        button.textContent = label;
        button.hidden = false;
        button.classList.toggle('active', activeTop === tab);
        button.setAttribute('aria-current', activeTop === tab ? 'page' : 'false');
        tabs.appendChild(button);
      });

      TOP_TABS.forEach(([tab]) => {
        const matches = [...tabs.querySelectorAll(`[data-owner-console-tab="${tab}"]`)];
        matches.slice(1).forEach(button => button.remove());
      });
    } finally {
      mutating = false;
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(canonicalize);
  }

  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  schedule();
})();