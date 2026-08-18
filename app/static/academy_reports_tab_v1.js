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
    return `<section class="academy-section-head"><div><span class="academy-kicker">ACADEMY OPERATIONS</span><h1>Reports</h1><p>Operational and financial reporting will live inside Academy rather than as a separate top-level navigation item.</p></div></section>
      <article class="panel"><div class="panel-head"><div><h2>Academy Reports</h2><p>The reporting workspace is positioned here now; report generation/export is part of the upcoming Academy completion work.</p></div><span class="academy-badge">PLANNED</span></div>
      <div class="academy-module-grid">${reports.map(([title,text])=>`<article class="academy-module" style="cursor:default"><span class="academy-module-icon">▤</span><span class="academy-module-copy"><strong>${title}</strong><small>${text}</small></span><span class="academy-module-meta">Planned</span></article>`).join('')}</div></article>`;
  }

  function ensureReportsTab(){
    const tabs=qs('#academyWorkspace .academy-tabs');
    if(!tabs)return;

    let button=qs('[data-academy-reports-tab]',tabs);
    if(!button){
      button=document.createElement('button');
      button.type='button';
      button.dataset.academyReportsTab='1';
      button.textContent='Reports';
      button.onclick=()=>{location.hash='academy?tab=reports';};
      tabs.appendChild(button);
    }

    // Keep Reports immediately beside Player Reviews when that tab is present.
    const reviews=qs('[data-academy-reviews-tab]',tabs);
    if(reviews && reviews.nextElementSibling!==button) reviews.after(button);

    const info=route();
    if(info.page==='academy'&&info.tab==='reports'){
      qsa('button',tabs).forEach(btn=>btn.classList.toggle('active',btn===button));
    } else {
      button.classList.remove('active');
    }
  }

  function renderReports(){
    const info=route();
    if(info.page!=='academy'||info.tab!=='reports')return;
    const content=qs('#academyWorkspace .academy-content');
    if(!content)return;
    if(!qs('.academy-reports-shell',content)){
      content.innerHTML=`<section class="academy-reports-shell">${reportsView()}</section>`;
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
