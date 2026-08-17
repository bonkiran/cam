(() => {
  const qs = (s, r=document) => r.querySelector(s);
  const qsa = (s, r=document) => [...r.querySelectorAll(s)];
  let applying = false;

  function currentPage(){
    return (location.hash.replace(/^#/, '').split('?')[0] || 'dashboard');
  }

  const GROUPS = [
    {
      key:'analysis', label:'Analysis', icon:'◈', parentRoute:null,
      children:[
        ['upload','⇧','Upload Video'],
        ['analyses','▣','My Analyses'],
        ['comparisons','⇄','Comparisons'],
        ['reports','▤','Reports']
      ]
    },
    {
      key:'academy', label:'Academy', icon:'▦', parentRoute:'academy',
      children:[
        ['players','♙','Players'],
        ['reports','▤','Reports']
      ]
    },
    {
      key:'insights', label:'Insights', icon:'⌁', parentRoute:'insights',
      children:[['shot-library','◫','Shot Library']]
    }
  ];

  function groupActive(group, page){
    return page === group.parentRoute || group.children.some(([route]) => route === page);
  }

  function setOpen(wrapper, parent, group, open){
    wrapper.classList.toggle('open', open);
    parent.setAttribute('aria-expanded', open ? 'true' : 'false');
    localStorage.setItem(`crick-nav-group-${group.key}`, open ? '1' : '0');
  }

  function makeChild(route, icon, label){
    const btn = document.createElement('button');
    btn.dataset.route = route;
    btn.className = 'nav-group-child';
    btn.innerHTML = `<i>${icon}</i><b>${label}</b>`;
    btn.onclick = () => { location.hash = route; };
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
      if(group.parentRoute) anchor = qs(`:scope > button[data-route="${group.parentRoute}"]`, nav);
      if(!anchor){
        for(const [route] of group.children){
          anchor = qs(`:scope > button[data-route="${route}"]`, nav);
          if(anchor) break;
        }
      }
      if(anchor) nav.insertBefore(wrapper, anchor); else nav.appendChild(wrapper);
    }

    const parent = qs('.nav-group-parent', wrapper);
    const submenu = qs('.nav-group-submenu', wrapper);
    if(!parent || !submenu) return;

    // Keep Dashboard completely standalone: no wrapper/group is created for it.
    // Academy and Insights are both route targets and expandable accordion parents.
    parent.onclick = (event) => {
      const isOpen = wrapper.classList.contains('open');
      const clickedCaret = event.target?.classList?.contains('nav-group-caret');

      // For grouped route parents (Academy / Insights):
      // - clicking the caret only toggles
      // - clicking the label/icon navigates when collapsed, and collapses when already open
      if(group.parentRoute){
        if(clickedCaret || isOpen){
          event.preventDefault();
          event.stopPropagation();
          setOpen(wrapper, parent, group, !isOpen);
          return;
        }
        setOpen(wrapper, parent, group, true);
        location.hash = group.parentRoute;
        return;
      }

      // Analysis is a pure accordion parent.
      setOpen(wrapper, parent, group, !isOpen);
    };

    // Build child buttons. Reports intentionally appears under both Analysis and Academy.
    for(const [route, icon, label] of group.children){
      let child = qs(`button[data-route="${route}"]`, submenu);
      if(!child){
        // Reuse the original direct button only once. For duplicate placements (Reports), clone/create.
        const direct = qs(`:scope > button[data-route="${route}"]`, nav);
        const alreadyGrouped = qs(`.nav-group-submenu button[data-route="${route}"]`, nav);
        if(direct && !alreadyGrouped){
          child = direct;
          submenu.appendChild(child);
        } else {
          child = makeChild(route, icon, label);
          submenu.appendChild(child);
        }
      }
      child.classList.add('nav-group-child');
      child.classList.toggle('active', currentPage() === route);
      child.onclick = () => { location.hash = route; };
    }

    const page = currentPage();
    const active = groupActive(group, page);
    const stored = localStorage.getItem(`crick-nav-group-${group.key}`);
    // Active child/group opens automatically only if the user has not explicitly collapsed it.
    const open = stored === '1' ? true : stored === '0' ? false : active;
    wrapper.classList.toggle('active', active);
    parent.classList.toggle('active', active);
    wrapper.classList.toggle('open', open);
    parent.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function cleanup(nav){
    // Remove legacy wrappers/scripts' DOM output before applying the canonical structure.
    const legacyAnalysis = qs('.analysis-nav-group', nav);
    if(legacyAnalysis){
      const oldSub = qs('.analysis-nav-submenu', legacyAnalysis);
      if(oldSub) qsa('button[data-route]', oldSub).forEach(btn => nav.insertBefore(btn, legacyAnalysis));
      legacyAnalysis.remove();
    }

    // Remove any obsolete Dashboard accordion created by v2, but preserve its child Report button.
    const oldDashboard = qs('.nav-group[data-nav-group="dashboard"]', nav);
    if(oldDashboard){
      const oldSub = qs('.nav-group-submenu', oldDashboard);
      if(oldSub) qsa('button[data-route]', oldSub).forEach(btn => nav.insertBefore(btn, oldDashboard));
      oldDashboard.remove();
    }

    // Sessions is no longer part of navigation.
    qsa('button[data-route="sessions"]', nav).forEach(btn => btn.remove());
  }

  function apply(){
    if(applying) return;
    applying = true;
    try{
      const nav = qs('.sidebar .nav');
      if(!nav) return;

      cleanup(nav);

      // Ensure Dashboard remains a plain, direct menu item.
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

      // Remove original direct entries once grouped. Dashboard stays standalone.
      const groupedRoutes = new Set(['upload','analyses','comparisons','reports','players','shot-library']);
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
