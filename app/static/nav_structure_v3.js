(() => {
  const qs = (s, r=document) => r.querySelector(s);
  const qsa = (s, r=document) => [...r.querySelectorAll(s)];
  let applying = false;

  function currentPage(){
    return (location.hash.replace(/^#/, '').split('?')[0] || 'dashboard');
  }

  const GROUPS = [
    {
      key:'analysis', label:'Analysis', icon:'◈',
      children:[
        ['upload','⇧','Upload Video'],
        ['analyses','▣','My Analyses'],
        ['comparisons','⇄','Comparisons'],
        ['reports','▤','Reports']
      ]
    },
    {
      key:'academy', label:'Academy', icon:'▦',
      children:[
        ['academy','⌂','Overview'],
        ['players','♙','Players'],
        ['reports','▤','Reports']
      ]
    },
    {
      key:'insights', label:'Insights', icon:'⌁',
      children:[
        ['insights','⌂','Overview'],
        ['shot-library','◫','Shot Library']
      ]
    }
  ];

  function reportsContext(){
    return localStorage.getItem('crick-reports-context') || 'analysis';
  }

  function groupOwnsPage(group, page){
    if(page === 'reports') return group.key === reportsContext();
    return group.children.some(([route]) => route === page);
  }

  function setOpen(wrapper, parent, group, open){
    wrapper.classList.toggle('open', open);
    parent.setAttribute('aria-expanded', open ? 'true' : 'false');
    localStorage.setItem(`crick-nav-group-${group.key}`, open ? '1' : '0');
  }

  function childButton(route, icon, label){
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.dataset.route = route;
    btn.className = 'nav-group-child';
    btn.innerHTML = `<i>${icon}</i><b>${label}</b>`;
    return btn;
  }

  function ensureGroup(nav, group){
    let wrapper = qs(`.nav-group[data-nav-group="${group.key}"]`, nav);
    if(!wrapper){
      wrapper = document.createElement('div');
      wrapper.className = 'nav-group';
      wrapper.dataset.navGroup = group.key;
      wrapper.innerHTML = `
        <button type="button" class="nav-group-parent" data-nav-group-parent="${group.key}" aria-expanded="false">
          <i>${group.icon}</i><b>${group.label}</b><span class="nav-group-caret">⌄</span>
        </button>
        <div class="nav-group-submenu"></div>`;

      let anchor = null;
      for(const [route] of group.children){
        anchor = qs(`:scope > button[data-route="${route}"]`, nav);
        if(anchor) break;
      }
      if(anchor) nav.insertBefore(wrapper, anchor); else nav.appendChild(wrapper);
    }

    const parent = qs('.nav-group-parent', wrapper);
    const submenu = qs('.nav-group-submenu', wrapper);
    if(!parent || !submenu) return;

    // Parent is a true accordion control: every click toggles open/closed.
    parent.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      setOpen(wrapper, parent, group, !wrapper.classList.contains('open'));
    };

    for(const [route, icon, label] of group.children){
      let child = qs(`button[data-route="${route}"]`, submenu);
      if(!child){
        // Reuse a direct menu button if available; otherwise create one.
        // Reports is intentionally represented in both Analysis and Academy.
        const direct = qs(`:scope > button[data-route="${route}"]`, nav);
        const alreadyUsed = qs(`.nav-group-submenu button[data-route="${route}"]`, nav);
        if(direct && !alreadyUsed){
          child = direct;
          submenu.appendChild(child);
        } else {
          child = childButton(route, icon, label);
          submenu.appendChild(child);
        }
      }

      child.classList.add('nav-group-child');
      child.classList.toggle('active', groupOwnsPage(group, currentPage()) && currentPage() === route);
      child.onclick = () => {
        if(route === 'reports') localStorage.setItem('crick-reports-context', group.key);
        setOpen(wrapper, parent, group, true);
        location.hash = route;
      };
    }

    const page = currentPage();
    const active = groupOwnsPage(group, page);
    const stored = localStorage.getItem(`crick-nav-group-${group.key}`);
    const open = stored === '1' ? true : stored === '0' ? false : active;

    wrapper.classList.toggle('active', active);
    parent.classList.toggle('active', active);
    wrapper.classList.toggle('open', open);
    parent.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function unwrap(wrapper, nav){
    if(!wrapper) return;
    const submenu = qs('.nav-group-submenu, .analysis-nav-submenu', wrapper);
    if(submenu){
      qsa('button[data-route]', submenu).forEach(btn => nav.insertBefore(btn, wrapper));
    }
    wrapper.remove();
  }

  function cleanup(nav){
    // Remove old versions of the generated navigation structure.
    unwrap(qs('.analysis-nav-group', nav), nav);
    unwrap(qs('.nav-group[data-nav-group="dashboard"]', nav), nav);

    // Sessions is intentionally removed from navigation.
    qsa('button[data-route="sessions"]', nav).forEach(btn => btn.remove());
  }

  function apply(){
    if(applying) return;
    applying = true;
    try{
      const nav = qs('.sidebar .nav');
      if(!nav) return;

      cleanup(nav);

      // Dashboard is deliberately standalone with NO submenu.
      let dashboard = qs(':scope > button[data-route="dashboard"]', nav);
      if(!dashboard){
        dashboard = document.createElement('button');
        dashboard.dataset.route = 'dashboard';
        dashboard.innerHTML = '<i>⌂</i><b>Dashboard</b>';
        dashboard.onclick = () => { location.hash = 'dashboard'; };
        nav.prepend(dashboard);
      }
      dashboard.classList.toggle('active', currentPage() === 'dashboard');

      GROUPS.forEach(group => ensureGroup(nav, group));

      // Remove top-level copies after their grouped versions have been created.
      const groupedRoutes = new Set([
        'upload','analyses','comparisons','reports',
        'academy','players','insights','shot-library'
      ]);
      qsa(':scope > button[data-route]', nav).forEach(btn => {
        if(groupedRoutes.has(btn.dataset.route)) btn.remove();
      });
    } finally {
      applying = false;
    }
  }

  const observer = new MutationObserver(apply);
  observer.observe(document.documentElement, {childList:true, subtree:true});
  window.addEventListener('hashchange', () => setTimeout(apply, 0));
  document.addEventListener('DOMContentLoaded', apply);
  apply();
})();
