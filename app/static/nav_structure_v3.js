(() => {
  const qs = (s, r=document) => r.querySelector(s);
  const qsa = (s, r=document) => [...r.querySelectorAll(s)];
  let applying = false;

  function routeInfo(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    const params=new URLSearchParams(query);
    return {page:page||'dashboard',tab:params.get('tab')||'overview'};
  }

  const GROUPS = [
    {
      key:'analysis', label:'Analysis', icon:'◈',
      children:[
        ['dashboard','⌂','Overview'],
        ['upload','⇧','Upload Video'],
        ['analyses','▣','My Analyses'],
        ['comparisons','⇄','Comparisons']
      ]
    },
    {
      key:'academy', label:'Academy', icon:'▦',
      children:[
        ['academy','⌂','Overview']
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

  function childTarget(group, route){
    return route;
  }

  function childIsActive(group, route){
    const info=routeInfo();
    if(group.key==='academy' && route==='academy') return info.page==='academy' && info.tab==='overview';
    return info.page===route;
  }

  function groupOwnsPage(group){
    const info=routeInfo();
    if(group.key==='academy' && info.page==='academy') return true;
    return group.children.some(([route])=>route===info.page);
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
      if(anchor){
        nav.insertBefore(wrapper, anchor);
      } else if(group.key==='academy'){
        const analysis=qs('.nav-group[data-nav-group="analysis"]',nav);
        if(analysis) analysis.after(wrapper); else nav.prepend(wrapper);
      } else {
        nav.appendChild(wrapper);
      }
    }

    const parent = qs('.nav-group-parent', wrapper);
    const submenu = qs('.nav-group-submenu', wrapper);
    if(!parent || !submenu) return;

    parent.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      setOpen(wrapper, parent, group, !wrapper.classList.contains('open'));
    };

    for(const [route, icon, label] of group.children){
      let child = qs(`button[data-route="${route}"]`, submenu);
      if(!child){
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

      // Normalize the display label even when a legacy direct button is reused.
      child.innerHTML = `<i>${icon}</i><b>${label}</b>`;
      child.classList.add('nav-group-child');
      child.classList.toggle('active', childIsActive(group,route));
      child.onclick = () => {
        setOpen(wrapper, parent, group, true);
        location.hash = childTarget(group,route);
      };
    }

    const active = groupOwnsPage(group);
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
    unwrap(qs('.analysis-nav-group', nav), nav);
    unwrap(qs('.nav-group[data-nav-group="dashboard"]', nav), nav);
    qsa('button[data-route="sessions"]', nav).forEach(btn => btn.remove());
  }

  function apply(){
    if(applying) return;
    applying = true;
    try{
      const nav = qs('.sidebar .nav');
      if(!nav) return;

      cleanup(nav);
      GROUPS.forEach(group => ensureGroup(nav, group));

      // Keep legacy direct buttons out of the top-level sidebar. Players and Reports
      // now live inside the Academy workspace; Dashboard is Analysis > Overview.
      const groupedRoutes = new Set([
        'dashboard','upload','analyses','comparisons','reports',
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
