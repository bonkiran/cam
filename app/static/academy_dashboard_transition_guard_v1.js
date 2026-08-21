(() => {
  const STYLE_ID = 'c17-dashboard-transition-guard-style';
  let scheduled = false;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    return {page: page || 'dashboard', tab: new URLSearchParams(query).get('tab') || 'overview'};
  }

  function overviewActive() {
    const r = route();
    return r.page === 'academy' && r.tab === 'overview';
  }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .c17-transition-shell{display:grid;gap:12px;min-height:520px}
      .c17-transition-top{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.7fr);gap:12px}
      .c17-transition-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}
      .c17-transition-card{min-height:112px;border:1px solid rgba(14,82,52,.13);border-radius:13px;background:rgba(255,255,255,.94);box-shadow:0 5px 18px rgba(0,55,35,.06);padding:16px;overflow:hidden}
      .c17-transition-card.tall{min-height:255px;grid-column:1/-1}
      .c17-transition-line{height:11px;border-radius:999px;background:linear-gradient(90deg,rgba(20,104,65,.08),rgba(20,104,65,.18),rgba(20,104,65,.08));background-size:220% 100%;animation:c17TransitionShimmer 1.2s linear infinite;margin:8px 0}
      .c17-transition-line.title{height:18px;width:38%}
      .c17-transition-line.medium{width:64%}
      .c17-transition-line.short{width:28%}
      .c17-transition-status{font-size:12px;font-weight:700;color:#246a4b;margin-bottom:7px}
      @keyframes c17TransitionShimmer{0%{background-position:220% 0}100%{background-position:-220% 0}}
      @media(max-width:900px){.c17-transition-top,.c17-transition-grid{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function loadingMarkup() {
    return `
      <div class="c17-dashboard c17-transition-shell" data-c17-transition-guard="1" aria-busy="true" aria-label="Loading C17 Academy Dashboard">
        <div class="c17-transition-top">
          <div class="c17-transition-card">
            <div class="c17-transition-status">Loading C17 Academy Dashboard…</div>
            <div class="c17-transition-line title"></div>
            <div class="c17-transition-line medium"></div>
          </div>
          <div class="c17-transition-card">
            <div class="c17-transition-line short"></div>
            <div class="c17-transition-line medium"></div>
            <div class="c17-transition-line"></div>
          </div>
        </div>
        <div class="c17-transition-grid">
          <div class="c17-transition-card"><div class="c17-transition-line title"></div><div class="c17-transition-line"></div><div class="c17-transition-line medium"></div></div>
          <div class="c17-transition-card"><div class="c17-transition-line title"></div><div class="c17-transition-line"></div><div class="c17-transition-line medium"></div></div>
          <div class="c17-transition-card tall"><div class="c17-transition-line title"></div><div class="c17-transition-line"></div><div class="c17-transition-line"></div><div class="c17-transition-line"></div><div class="c17-transition-line medium"></div></div>
        </div>
      </div>`;
  }

  function guardOldOverview() {
    scheduled = false;
    if (!overviewActive()) return;
    const content = document.querySelector('#academyWorkspace .academy-content');
    if (!content) return;

    // Once Dashboard v4 owns the surface, never interfere with it.
    if (content.dataset.dashboardV4 === '1') return;
    const liveV4 = content.querySelector('.c17-dashboard:not([data-c17-transition-guard])');
    if (liveV4) return;

    // academy_v3 renders its legacy overview first. Replace that legacy DOM in the
    // same mutation cycle, before the browser paints it, so users never see the old dashboard.
    const legacyOverview = content.querySelector(':scope > .academy-hero, :scope > .academy-stats, :scope > .academy-dashboard-grid');
    if (!legacyOverview) return;

    ensureStyle();
    content.innerHTML = loadingMarkup();
    content.dataset.c17TransitionGuard = '1';
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(guardOldOverview);
  }

  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(schedule).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
