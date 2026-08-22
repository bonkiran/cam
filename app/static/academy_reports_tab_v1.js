(() => {
  const qs=(s,r=document)=>r.querySelector(s);
  const qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  let applying=false;

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    const params=new URLSearchParams(query);
    return {page:page||'dashboard',tab:params.get('tab')||'overview'};
  }

  function reportsView(){
    const reports=[
      ['Player & Guardian Directory','Player/family contact and status directory.'],
      ['Enrollment Report','Active, frozen, trial and cancelled program enrollments.'],
      ['Batch Roster & Waitlist','Current batch capacity, roster and waitlisted players.'],
      ['Coach Schedule & Workload','Coach assignments and scheduled workload.'],
      ['Attendance Report','Session and player attendance summaries.'],
      ['Accounts Receivable','Outstanding, overdue and due-soon Academy balances.'],
      ['Payment Ledger','Payments, receipts, refunds and family-credit activity.'],
      ['Teams, Matches & Tournaments','Competition rosters, fixtures and tournament schedule.']
    ];
    return `<section class="cam-section-head"><div><span class="cam-kicker">ACADEMY OPERATIONS</span><h1>Reports</h1><p>Operational and financial reporting will live inside Academy rather than as a separate top-level navigation item.</p></div></section>
      <article class="panel"><div class="panel-head"><div><h2>Academy Reports</h2><p>The reporting workspace is positioned here now; report generation/export is part of the upcoming Academy completion work.</p></div><span class="cam-badge">PLANNED</span></div>
      <div class="cam-module-grid">${reports.map(([title,text])=>`<article class="cam-module" style="cursor:default"><span class="cam-module-icon">▤</span><span class="cam-module-copy"><strong>${title}</strong><small>${text}</small></span><span class="cam-module-meta">Planned</span></article>`).join('')}</div></article>`;
  }

  function ensureReportsTab(){
    const tabs=qs('#camWorkspace .cam-tabs');
    if(!tabs)return;

    let button=qs('[data-cam-reports-tab]',tabs);
    if(!button){
      button=document.createElement('button');
      button.type='button';
      button.dataset.camReportsTab='1';
      button.textContent='Reports';
      button.onclick=()=>{location.hash='cam?tab=reports';};
      tabs.appendChild(button);
    }

    // Keep Reports immediately beside Player Reviews when that tab is present.
    const reviews=qs('[data-cam-reviews-tab]',tabs);
    if(reviews && reviews.nextElementSibling!==button) reviews.after(button);

    const info=route();
    if(info.page==='cam'&&info.tab==='reports'){
      qsa('button',tabs).forEach(btn=>btn.classList.toggle('active',btn===button));
    } else {
      button.classList.remove('active');
    }
  }

  function renderReports(){
    const info=route();
    if(info.page!=='cam'||info.tab!=='reports')return;
    const content=qs('#camWorkspace .cam-content');
    if(!content)return;
    if(!qs('.cam-reports-shell',content)){
      content.innerHTML=`<section class="cam-reports-shell">${reportsView()}</section>`;
    }
  }

  function apply(){
    if(applying)return;
    applying=true;
    try{
      ensureReportsTab();
      renderReports();
    } finally {
      applying=false;
    }
  }

  const observer=new MutationObserver(()=>apply());
  observer.observe(document.documentElement,{childList:true,subtree:true});
  window.addEventListener('hashchange',()=>setTimeout(apply,0));
  document.addEventListener('DOMContentLoaded',apply);
  apply();
})();
