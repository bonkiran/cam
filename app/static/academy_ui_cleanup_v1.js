(() => {
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    return {page:page||'dashboard', tab:new URLSearchParams(query).get('tab')||'overview'};
  }

  function academyActive(){ return route().page === 'academy'; }

  const TITLE_MAP = new Map([
    ['Academy Players','Players'],
    ['Programs & Enrollment','Programs'],
    ['Academy Coaches','Coaches'],
    ['Fees & Payments','Finance'],
    ['Academy Reports','Reports'],
    ['Academy Settings','Settings'],
  ]);

  function normalizePageTitles(){
    if(!academyActive()) return;
    $$('#academyWorkspace .academy-content h1').forEach(h1 => {
      const replacement=TITLE_MAP.get((h1.textContent||'').trim());
      if(replacement && h1.textContent!==replacement) h1.textContent=replacement;
    });
  }

  function normalizeSearch(){
    const input=$('#globalSearch');
    if(!input) return;
    const wanted=academyActive() ? 'Search players, coaches, programs...' : 'Search analyses, players...';
    if(input.placeholder!==wanted) input.placeholder=wanted;
  }

  function normalizeSidebar(){
    const nav=$('.sidebar .nav');
    if(!nav) return;
    const hide=academyActive();
    ['settings','integrations'].forEach(routeName => {
      $$(`:scope > button[data-route="${routeName}"]`,nav).forEach(button => {
        button.hidden=hide;
        button.setAttribute('aria-hidden',hide?'true':'false');
      });
    });
  }

  function enrichLoadingState(){
    if(!academyActive()) return;
    const content=$('#academyWorkspace .academy-content');
    if(!content) return;
    const text=(content.textContent||'').trim();
    const loading=/^Loading\b/i.test(text) || /Loading (fees|billing|players|programs|coaches|reports|settings)/i.test(text);
    if(!loading){ content.classList.remove('cam-academy-loading'); return; }
    content.classList.add('cam-academy-loading');
    if($('.cam-ui-loading-skeleton',content)) return;
    const skeleton=document.createElement('div');
    skeleton.className='cam-ui-loading-skeleton';
    skeleton.setAttribute('aria-hidden','true');
    skeleton.innerHTML='<div></div><div></div><div></div>';
    content.appendChild(skeleton);
  }

  function markAcademyShell(){
    document.body.classList.toggle('cam-academy-context',academyActive());
  }

  let scheduled=false;
  function apply(){
    scheduled=false;
    markAcademyShell();
    normalizeSearch();
    normalizeSidebar();
    normalizePageTitles();
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
