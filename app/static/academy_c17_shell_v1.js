(() => {
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];
  let scheduled = false;
  let originalBrand = null;

  const ITEMS = [
    {label:'Dashboard', icon:'⌂', target:'academy', active:r => r.page==='academy' && r.tab==='overview'},
    {label:'Registration', icon:'✎', target:'academy?tab=registration', active:r => r.page==='academy' && r.tab==='registration'},
    {label:'Players', icon:'♙', target:'academy?tab=players', active:r => r.page==='academy' && r.tab==='players'},
    {label:'Programs', icon:'▤', target:'academy?tab=programs', active:r => r.page==='academy' && r.tab==='programs'},
    {label:'Coaches', icon:'♟', target:'academy?tab=coaches', active:r => r.page==='academy' && r.tab==='coaches'},
    {label:'Finance', icon:'$', target:'academy?tab=fees', active:r => r.page==='academy' && r.tab==='fees'},
    {label:'Reports', icon:'▥', target:'academy?tab=reports', active:r => r.page==='academy' && r.tab==='reports'},
    {label:'Settings', icon:'⚙', target:'academy?tab=setup', active:r => r.page==='academy' && r.tab==='setup'},
    {label:'Insights', icon:'⌁', target:'insights', active:r => r.page==='insights'},
    {label:'Help & Support', icon:'?', target:'help', active:r => r.page==='help'}
  ];
  const NAV_SIGNATURE = ITEMS.map(item => `${item.label}:${item.target}`).join('|');

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query=''] = raw.split('?');
    return {page:page || 'academy', tab:new URLSearchParams(query).get('tab') || 'overview'};
  }

  function academyMode() { return route().page === 'academy'; }

  function brandMarkup() {
    return `<img class="c17-brand-logo" src="/static/c17_academy_logo.png" alt="C17 Cricket Academy"><div class="c17-brand-copy"><strong>C17</strong><span>CRICKET ACADEMY</span></div>`;
  }

  function ensureBrand() {
    const brand = $('.sidebar .brand');
    if (!brand) return;
    if (originalBrand === null) originalBrand = brand.innerHTML;
    if (academyMode()) {
      if (!brand.dataset.c17Brand) {
        brand.innerHTML = brandMarkup();
        brand.dataset.c17Brand = '1';
      }
    } else if (brand.dataset.c17Brand) {
      brand.innerHTML = originalBrand || brand.innerHTML;
      delete brand.dataset.c17Brand;
    }
  }

  function buildAcademyNav(holder) {
    holder.innerHTML = ITEMS.map(item => `<button type="button" class="c17-nav-item" data-c17-target="${item.target}"><i>${item.icon}</i><b>${item.label}</b></button>`).join('');
    holder.dataset.c17Signature = NAV_SIGNATURE;
  }

  function setActiveTarget(holder, target) {
    $$('[data-c17-target]', holder).forEach(button => {
      const selected = button.dataset.c17Target === target;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-current', selected ? 'page' : 'false');
    });
  }

  function updateActive(holder) {
    const r = route();
    ITEMS.forEach(item => {
      const button = $(`[data-c17-target="${item.target}"]`, holder);
      if (!button) return;
      const selected = Boolean(item.active(r));
      button.classList.toggle('active', selected);
      button.setAttribute('aria-current', selected ? 'page' : 'false');
    });
  }

  function wireAcademyNav(holder) {
    if (holder.dataset.c17Wired === '1') return;
    holder.addEventListener('click', event => {
      const button = event.target.closest('[data-c17-target]');
      if (!button || !holder.contains(button)) return;
      event.preventDefault();
      const target = button.dataset.c17Target;
      if (!target) return;

      // Give the user immediate visual feedback before async route/data work starts.
      // Hash-change reconciliation below remains the source of truth afterward.
      setActiveTarget(holder, target);

      const next = `#${target}`;
      if (location.hash === next) {
        window.dispatchEvent(new HashChangeEvent('hashchange'));
      } else {
        location.hash = target;
      }
    });
    holder.dataset.c17Wired = '1';
  }

  function ensureAcademyNav() {
    const nav = $('.sidebar .nav');
    if (!nav || !academyMode()) return;
    let holder = $(':scope > .c17-sidebar-nav', nav);
    if (!holder) {
      holder = document.createElement('div');
      holder.className = 'c17-sidebar-nav';
      nav.appendChild(holder);
    }

    if (holder.dataset.c17Signature !== NAV_SIGNATURE || holder.querySelectorAll('[data-c17-target]').length !== ITEMS.length) {
      buildAcademyNav(holder);
    }
    wireAcademyNav(holder);
    updateActive(holder);
  }

  function apply() {
    scheduled = false;
    const mode = academyMode();
    document.body.classList.toggle('c17-academy-mode', mode);
    ensureBrand();
    if (mode) ensureAcademyNav();
    else $$('.c17-sidebar-nav').forEach(el => el.remove());
  }

  function schedule() { if (scheduled) return; scheduled = true; requestAnimationFrame(apply); }
  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(schedule).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
