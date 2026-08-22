(() => {
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    return {page:page||'dashboard', tab:new URLSearchParams(query).get('tab')||'overview'};
  }

  function camActive(){ return route().page === 'cam'; }

  const TITLE_MAP = new Map([
    ['Academy Players','Players'],
    ['Programs & Enrollment','Programs'],
    ['Academy Coaches','Coaches'],
    ['Fees & Payments','Finance'],
    ['Academy Reports','Reports'],
    ['Academy Settings','Settings'],
  ]);

  function normalizePageTitles(){
    if(!camActive()) return;
    $$('#camWorkspace .cam-content h1').forEach(h1 => {
      const replacement=TITLE_MAP.get((h1.textContent||'').trim());
      if(replacement && h1.textContent!==replacement) h1.textContent=replacement;
    });
  }

  function normalizeSearch(){
    const input=$('#globalSearch');
    if(!input) return;
    const wanted=camActive() ? 'Search players, coaches, programs...' : 'Search analyses, players...';
    if(input.placeholder!==wanted) input.placeholder=wanted;
  }

  function replaceExactText(selector, from, to){
    $$(selector).forEach(node=>{
      if((node.textContent||'').trim()===from) node.textContent=to;
    });
  }

  function polishDashboard(){
    const content=$('#camWorkspace .cam-content');
    if(!content) return;
    const dashboard=camActive() && route().tab==='overview';
    content.classList.toggle('cam-owner-dashboard-polished',dashboard);
    if(!dashboard) return;

    replaceExactText('button','Fees & Payments','Finance');
    replaceExactText('button','Teams & Matches','Matches');
    replaceExactText('button','Sessions','Programs & Sessions');

    $$('*',content).forEach(node=>{
      if(node.children.length) return;
      const text=(node.textContent||'').trim();
      if(text==='Finance ledger not enabled yet') node.textContent='Finance tracking not configured yet';
      if(text==='Weather.com connection is ready for a server API key.') node.textContent='Weekend weather will appear when the academy weather integration is configured.';
    });
  }

  function enrichLoadingState(){
    if(!camActive()) return;
    const content=$('#camWorkspace .cam-content');
    if(!content) return;
    const text=(content.textContent||'').trim();
    const loading=/^Loading\b/i.test(text) || /Loading (fees|billing|players|programs|coaches|reports|settings)/i.test(text);
    if(!loading){ content.classList.remove('cam-cam-loading'); return; }
    content.classList.add('cam-cam-loading');
    if($('.cam-ui-loading-skeleton',content)) return;
    const skeleton=document.createElement('div');
    skeleton.className='cam-ui-loading-skeleton';
    skeleton.setAttribute('aria-hidden','true');
    skeleton.innerHTML='<div></div><div></div><div></div>';
    content.appendChild(skeleton);
  }

  function markAcademyShell(){
    document.body.classList.toggle('cam-cam-context',camActive());
  }

  let scheduled=false;
  function apply(){
    scheduled=false;
    markAcademyShell();
    normalizeSearch();
    normalizePageTitles();
    polishDashboard();
    enrichLoadingState();
  }
  function schedule(){
    if(scheduled) return;
    scheduled=true;
    requestAnimationFrame(apply);
  }

  window.addEventListener('hashchange',schedule);
  document.addEventListener('DOMContentLoaded',schedule);
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
  schedule();
})();
