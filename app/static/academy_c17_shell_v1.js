(() => {
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];
  let scheduled = false;
  let originalBrand = null;

  const ITEMS = [
    {label:'Dashboard', icon:'⌂', target:'dashboard', active:r => r.page==='dashboard'},
    {label:'Academy', icon:'▦', target:'academy', active:r => r.page==='academy' && r.tab==='overview'},
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

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query=''] = raw.split('?');
    return {page:page || 'dashboard', tab:new URLSearchParams(query).get('tab') || 'overview'};
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

  function ensureAcademyNav() {
    const nav = $('.sidebar .nav');
    if (!nav || !academyMode()) return;
    let holder = $(':scope > .c17-sidebar-nav', nav);
    if (!holder) {
      holder = document.createElement('div');
      holder.className = 'c17-sidebar-nav';
      nav.appendChild(holder);
    }
    const r = route();
    holder.innerHTML = ITEMS.map(item => `<button type="button" class="c17-nav-item ${item.active(r)?'active':''}" data-c17-target="${item.target}"><i>${item.icon}</i><b>${item.label}</b></button>`).join('');
    $$('[data-c17-target]', holder).forEach(button => button.onclick = () => { location.hash = button.dataset.c17Target; });
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
