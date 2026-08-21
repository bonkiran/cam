(() => {
  const ROUTE_CLASS = 'c17-overview-first-paint';
  const READY_CLASS = 'c17-overview-ready';
  const SHELL_ID = 'c17DashboardFirstPaint';
  let scheduled = false;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    return {page: page || 'dashboard', tab: new URLSearchParams(query).get('tab') || 'overview'};
  }

  function active() {
    const r = route();
    return r.page === 'academy' && r.tab === 'overview';
  }

  function skeletonMarkup() {
    const bars = (count, cls = '') => Array.from({length: count}, (_, i) => `<span class="c17-fp-bar ${cls}" style="--w:${74 - (i % 3) * 11}%"></span>`).join('');
    return `<div class="c17-fp-dashboard" aria-hidden="true">
      <section class="c17-fp-hero">
        <div class="c17-fp-welcome"><span class="c17-fp-line xl"></span><span class="c17-fp-line md"></span></div>
        <div class="c17-fp-weather"><div class="c17-fp-weather-now"><span class="c17-fp-circle"></span>${bars(3)}</div><div class="c17-fp-days">${Array.from({length:7},()=>'<span></span>').join('')}</div></div>
      </section>
      <section class="c17-fp-two"><article class="c17-fp-card"><span class="c17-fp-title"></span><div class="c17-fp-programs">${Array.from({length:6},()=>'<i></i>').join('')}</div></article><article class="c17-fp-card"><span class="c17-fp-title"></span><div class="c17-fp-table">${bars(3,'wide')}</div></article></section>
      <article class="c17-fp-card"><span class="c17-fp-title lg"></span><div class="c17-fp-table rows-4">${bars(5,'wide')}</div></article>
      <article class="c17-fp-card"><span class="c17-fp-title"></span><div class="c17-fp-two compact"><div class="c17-fp-table">${bars(4,'wide')}</div><div class="c17-fp-table">${bars(3,'wide')}</div></div></article>
      <article class="c17-fp-card"><span class="c17-fp-title"></span><div class="c17-fp-three">${Array.from({length:3},()=>'<i></i>').join('')}</div></article>
      <article class="c17-fp-card"><span class="c17-fp-title"></span><div class="c17-fp-table">${bars(5,'wide')}</div></article>
      <section class="c17-fp-two"><article class="c17-fp-card"><span class="c17-fp-title"></span><div class="c17-fp-money">${Array.from({length:2},()=>'<i></i>').join('')}</div></article><article class="c17-fp-card"><span class="c17-fp-title"></span><div class="c17-fp-money three">${Array.from({length:3},()=>'<i></i>').join('')}</div></article></section>
    </div>`;
  }

  function removeTransitionSnapshot() {
    document.getElementById('academyTransitionSnapshot')?.remove();
    document.documentElement.classList.remove('academy-tab-transitioning');
    delete document.documentElement.dataset.academyTransitionTarget;
  }

  function ensureShell() {
    const main = document.querySelector('#app .main');
    if (!main) return null;
    let shell = document.getElementById(SHELL_ID);
    if (!shell) {
      shell = document.createElement('div');
      shell.id = SHELL_ID;
      shell.innerHTML = skeletonMarkup();
      const topbar = main.querySelector(':scope > .topbar');
      if (topbar && topbar.nextSibling) main.insertBefore(shell, topbar.nextSibling);
      else main.appendChild(shell);
    }
    return shell;
  }

  function dashboardV4OwnsWorkspace() {
    const content = document.querySelector('#academyWorkspace .academy-content');
    // Dashboard v4 sets this marker after either a successful prototype render or
    // its own error state. Either way, the legacy Academy overview no longer owns
    // the visible workspace and the first-paint shell can safely hand off.
    return Boolean(content && content.dataset.dashboardV4 === '1');
  }

  function apply() {
    scheduled = false;
    const root = document.documentElement;
    if (!active()) {
      root.classList.remove(ROUTE_CLASS, READY_CLASS);
      document.getElementById(SHELL_ID)?.remove();
      return;
    }

    root.classList.add(ROUTE_CLASS);

    if (dashboardV4OwnsWorkspace()) {
      root.classList.add(READY_CLASS);
      document.getElementById(SHELL_ID)?.remove();
      return;
    }

    root.classList.remove(READY_CLASS);
    removeTransitionSnapshot();
    ensureShell();
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(apply);
  }

  window.addEventListener('hashchange', schedule, true);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(schedule).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
