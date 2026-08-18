(() => {
  const TABS = [
    ['dashboard','Overview'],
    ['upload','Upload Video'],
    ['analyses','My Analyses'],
    ['comparisons','Comparisons']
  ];
  const ANALYSIS_ROUTES = new Set(['dashboard','upload','analyses','analysis','comparisons']);
  let applying = false;

  function currentPage(){
    const raw=location.hash.replace(/^#/,'')||'dashboard';
    return raw.split('?')[0]||'dashboard';
  }

  function activeRoute(page){
    return page==='analysis' ? 'analyses' : page;
  }

  function buildTabs(){
    const nav=document.createElement('div');
    nav.id='analysisWorkspaceTabs';
    nav.className='analysis-workspace-tabs';
    nav.setAttribute('aria-label','Analysis workspace');
    for(const [route,label] of TABS){
      const button=document.createElement('button');
      button.type='button';
      button.dataset.analysisRoute=route;
      button.textContent=label;
      button.onclick=()=>{ location.hash=route; };
      nav.appendChild(button);
    }
    return nav;
  }

  function apply(){
    if(applying) return;
    applying=true;
    try{
      const page=currentPage();
      const main=document.querySelector('#app .main');
      const existing=document.getElementById('analysisWorkspaceTabs');

      if(!ANALYSIS_ROUTES.has(page)){
        if(existing) existing.remove();
        return;
      }
      if(!main) return;

      let tabs=existing;
      if(!tabs){
        tabs=buildTabs();
        const topbar=main.querySelector(':scope > .topbar');
        if(topbar) topbar.after(tabs); else main.prepend(tabs);
      }

      const active=activeRoute(page);
      [...tabs.querySelectorAll('button[data-analysis-route]')].forEach(button=>{
        const selected=button.dataset.analysisRoute===active;
        button.classList.toggle('active',selected);
        button.setAttribute('aria-current',selected?'page':'false');
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
