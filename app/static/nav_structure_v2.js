(() => {
  const qs=(s,r=document)=>r.querySelector(s);
  const qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  let applying=false;

  function currentPage(){
    return (location.hash.replace(/^#/,'').split('?')[0] || 'dashboard');
  }

  const GROUPS = [
    {
      key:'dashboard', label:'Dashboard', icon:'⌂', parentRoute:'dashboard',
      children:[['reports','▤','Reports']]
    },
    {
      key:'analysis', label:'Analysis', icon:'◈', parentRoute:null,
      children:[['upload','⇧','Upload Video'],['analyses','▣','My Analyses'],['comparisons','⇄','Comparisons']]
    },
    {
      key:'academy', label:'Academy', icon:'▦', parentRoute:'academy',
      children:[['players','♙','Players']]
    },
    {
      key:'insights', label:'Insights', icon:'⌁', parentRoute:'insights',
      children:[['shot-library','◫','Shot Library']]
    },
  ];

  function routeActive(group,page){
    if(group.parentRoute && page===group.parentRoute) return true;
    return group.children.some(([route])=>route===page);
  }

  function shouldOpen(group,page){
    if(routeActive(group,page)) return true;
    return localStorage.getItem(`crick-nav-group-${group.key}`)==='1';
  }

  function makeParent(group){
    const button=document.createElement('button');
    button.type='button';
    button.className='nav-group-parent';
    button.dataset.navGroupParent=group.key;
    button.innerHTML=`<i>${group.icon}</i><b>${group.label}</b><span class="nav-group-caret">⌄</span>`;
    button.title=group.label;
    return button;
  }

  function ensureGroup(nav,group){
    let wrapper=qs(`.nav-group[data-nav-group="${group.key}"]`,nav);
    let parentButton=group.parentRoute ? qs(`:scope > button[data-route="${group.parentRoute}"]`,nav) : null;

    if(!wrapper){
      wrapper=document.createElement('div');
      wrapper.className='nav-group';
      wrapper.dataset.navGroup=group.key;

      const parent=makeParent(group);
      const submenu=document.createElement('div');
      submenu.className='nav-group-submenu';
      wrapper.append(parent,submenu);

      const firstChildRoute=group.children[0]?.[0];
      const firstChild=firstChildRoute ? qs(`:scope > button[data-route="${firstChildRoute}"]`,nav) : null;
      const anchor=parentButton || firstChild;
      if(anchor) nav.insertBefore(wrapper,anchor); else nav.appendChild(wrapper);
    }

    const parent=qs('.nav-group-parent',wrapper);
    const submenu=qs('.nav-group-submenu',wrapper);
    if(!parent || !submenu) return;

    // A grouped top-level route such as Dashboard/Academy/Insights remains directly reachable.
    if(group.parentRoute){
      parent.onclick=(event)=>{
        const caretHit=event.target?.classList?.contains('nav-group-caret');
        if(caretHit){
          const next=!wrapper.classList.contains('open');
          wrapper.classList.toggle('open',next);
          parent.setAttribute('aria-expanded',next?'true':'false');
          localStorage.setItem(`crick-nav-group-${group.key}`,next?'1':'0');
          event.stopPropagation();
          return;
        }
        location.hash=group.parentRoute;
        wrapper.classList.add('open');
        parent.setAttribute('aria-expanded','true');
        localStorage.setItem(`crick-nav-group-${group.key}`,'1');
      };
      if(parentButton && parentButton!==parent){ parentButton.remove(); parentButton=null; }
    } else {
      parent.onclick=()=>{
        const next=!wrapper.classList.contains('open');
        wrapper.classList.toggle('open',next);
        parent.setAttribute('aria-expanded',next?'true':'false');
        localStorage.setItem(`crick-nav-group-${group.key}`,next?'1':'0');
      };
    }

    group.children.forEach(([route,icon,label])=>{
      let child=qs(`button[data-route="${route}"]`,submenu);
      if(!child){
        child=qs(`:scope > button[data-route="${route}"]`,nav);
        if(child) submenu.appendChild(child);
      }
      if(!child){
        child=document.createElement('button');
        child.dataset.route=route;
        child.innerHTML=`<i>${icon}</i><b>${label}</b>`;
        child.onclick=()=>{location.hash=route};
        submenu.appendChild(child);
      }
      child.classList.add('nav-group-child');
      child.classList.toggle('active',currentPage()===route);
      child.onclick=()=>{location.hash=route};
    });

    const page=currentPage();
    const active=routeActive(group,page);
    const open=shouldOpen(group,page);
    wrapper.classList.toggle('active',active);
    wrapper.classList.toggle('open',open);
    parent.classList.toggle('active',active);
    parent.setAttribute('aria-expanded',open?'true':'false');
  }

  function apply(){
    if(applying) return;
    applying=true;
    try{
      const nav=qs('.sidebar .nav');
      if(!nav) return;

      // Remove the obsolete Sessions navigation entry entirely.
      qsa(':scope > button[data-route="sessions"], .nav-group button[data-route="sessions"]',nav).forEach(x=>x.remove());

      // Remove the prior Analysis wrapper if the new structure has not absorbed it yet.
      const legacy=qs('.analysis-nav-group',nav);
      if(legacy){
        const sub=qs('.analysis-nav-submenu',legacy);
        if(sub){ qsa('button[data-route]',sub).forEach(btn=>nav.insertBefore(btn,legacy)); }
        legacy.remove();
      }

      GROUPS.forEach(group=>ensureGroup(nav,group));

      // Prevent duplicate direct menu items after grouping.
      const groupedRoutes=new Set(GROUPS.flatMap(g=>g.children.map(c=>c[0])));
      qsa(':scope > button[data-route]',nav).forEach(btn=>{
        if(groupedRoutes.has(btn.dataset.route) || btn.dataset.route==='sessions') btn.remove();
      });
    } finally {
      applying=false;
    }
  }

  const observer=new MutationObserver(apply);
  observer.observe(document.documentElement,{childList:true,subtree:true});
  window.addEventListener('hashchange',()=>setTimeout(apply,0));
  document.addEventListener('DOMContentLoaded',apply);
  apply();
})();
