(() => {
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];
  let scheduled = false;
  let originalBrand = null;

  const ITEMS = [
    {label:'Dashboard', icon:'⌂', target:'cam', active:r => r.page==='cam' && r.tab==='overview'},
    {label:'Enrollment', icon:'✎', target:'cam?tab=registration', active:r => r.page==='cam' && r.tab==='registration'},
    {label:'Players', icon:'♙', target:'cam?tab=players', active:r => r.page==='cam' && r.tab==='players'},
    {label:'Programs', icon:'▤', target:'cam?tab=programs', active:r => r.page==='cam' && r.tab==='programs'},
    {label:'Coaches', icon:'♟', target:'cam?tab=coaches', active:r => r.page==='cam' && r.tab==='coaches'},
    {label:'Finance', icon:'$', target:'cam?tab=fees', active:r => r.page==='cam' && r.tab==='fees'},
    {label:'Reports', icon:'▥', target:'cam?tab=reports', active:r => r.page==='cam' && r.tab==='reports'},
    {label:'Settings', icon:'⚙', target:'cam?tab=setup', active:r => r.page==='cam' && r.tab==='setup'},
    {label:'Integrations', icon:'↔', target:'integrations', active:r => r.page==='integrations'},
    {label:'Insights', icon:'⌁', target:'insights', active:r => r.page==='insights'},
    {label:'Help & Support', icon:'?', target:'help', active:r => r.page==='help'}
  ];
  const NAV_SIGNATURE = ITEMS.map(item => `${item.label}:${item.target}`).join('|');

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query=''] = raw.split('?');
    return {page:page || 'dashboard', tab:new URLSearchParams(query).get('tab') || 'overview'};
  }

  function camMode() {
    const page = route().page;
    return page === 'cam' || page === 'integrations';
  }

  function brandMarkup() {
    return `<img class="c17-brand-logo" src="/static/c17_academy_logo.png" alt="C17 Cricket Academy"><div class="c17-brand-copy"><strong>C17</strong><span>CRICKET ACADEMY</span></div>`;
  }

  function ensureBrand() {
    const brand = $('.sidebar .brand');
    if (!brand) return;
    if (originalBrand === null) originalBrand = brand.innerHTML;
    if (camMode()) {
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
    if (!nav || !camMode()) return;
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
    const mode = camMode();
    document.body.classList.toggle('c17-cam-mode', mode);
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