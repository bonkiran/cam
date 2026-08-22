(() => {
  const qs=(s,r=document)=>r.querySelector(s);
  const qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  const TABS=[
    ['overview','Overview'],['players','Players'],['batches','Batches & Sessions'],
    ['coaches','Coaches'],['attendance','Attendance'],['teams','Teams & Matches'],
    ['tournaments','Tournaments'],['fees','Fees & Payments']
  ];
  let renderToken=0;

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    const params=new URLSearchParams(query);
    return {page:page||'dashboard',tab:params.get('tab')||'overview'};
  }
  function go(tab='overview'){
    location.hash=tab==='overview'?'cam':`academy?tab=${encodeURIComponent(tab)}`;
  }
  async function getJson(url){
    const res=await fetch(url,{cache:'no-store'});
    if(!res.ok) throw new Error(`Request failed (${res.status})`);
    return res.json();
  }

  function ensureNav(){
    const nav=qs('.sidebar .nav');
    if(!nav) return;
    let btn=qs('[data-route="cam"]',nav);
    if(!btn){
      btn=document.createElement('button');
      btn.dataset.route='cam';
      btn.innerHTML='<i>▦</i><b>Academy</b>';
      btn.title='Academy Management';
      btn.onclick=()=>go('overview');
      const players=qs('[data-route="players"]',nav);
      if(players) players.insertAdjacentElement('afterend',btn); else nav.appendChild(btn);
    }
    qsa('button',nav).forEach(x=>{
      if(x.dataset.route==='cam') x.classList.toggle('active',route().page==='cam');
    });
  }

  function tabs(active){
    return `<div class="cam-tabs">${TABS.map(([id,label])=>`<button class="${id===active?'active':''}" data-cam-tab="${id}">${label}</button>`).join('')}</div>`;
  }
  function metric(label,value,note,kind='green'){
    const icon=kind==='green'?'♙':kind==='blue'?'▦':kind==='amber'?'◷':'◎';
    return `<article class="cam-stat ${kind}"><div class="cam-stat-icon">${icon}</div><div><span>${label}</span><strong>${value}</strong><small>${note}</small></div></article>`;
  }
  function moduleCard(icon,title,text,tab,meta='Foundation'){
    return `<button class="cam-module" data-cam-tab="${tab}"><span class="cam-module-icon">${icon}</span><span class="cam-module-copy"><strong>${title}</strong><small>${text}</small></span><span class="cam-module-meta">${meta}</span><b>→</b></button>`;
  }
  function foundation(title,description,fields){
    return `<section class="cam-two-col"><article class="panel cam-foundation-card"><div class="cam-kicker">ACADEMY OPERATIONS · FOUNDATION</div><h2>${title}</h2><p>${description}</p><div class="cam-field-list">${fields.map(x=>`<span>${x}</span>`).join('')}</div><div class="cam-foundation-note"><strong>No fabricated academy data.</strong> This module is the product foundation; persistence and workflows will be connected module-by-module.</div></article><article class="panel cam-link-card"><div class="cam-kicker">CONNECTED PLAYER DEVELOPMENT</div><h2>Use the same player record</h2><p>Academy operations attach to the existing CrickAnalysis player, video, event and biomechanics history instead of creating another player identity.</p><div class="cam-journey"><span>Enrollment</span><i>→</i><span>Session</span><i>→</i><span>Coach feedback</span><i>→</i><span>Video evidence</span><i>→</i><span>Progress</span></div></article></section>`;
  }
  function playerRows(players){
    if(!players.length) return `<div class="cam-empty"><strong>No academy players yet</strong><span>Upload footage with a player name to create the first unified player profile.</span></div>`;
    return players.map(p=>`<div class="cam-player-row"><div class="cam-avatar">${String(p.name||'?').split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase()}</div><div><strong>${p.name}</strong><small>${p.video_count||0} video(s) · ${p.completed_analyses||0} completed analysis(es)</small></div><span class="cam-status">Unified profile</span><button data-go-route="analyses">View development →</button></div>`).join('');
  }

  function overview(data){
    const players=data.players||[];
    const d=data.dashboard||{};
    const withAnalysis=players.filter(p=>Number(p.completed_analyses||0)>0).length;
    return `<section class="cam-hero"><div><span class="cam-kicker">ACADEMY + PERFORMANCE INTELLIGENCE</span><h1>Academy Dashboard</h1><p>Run the academy and develop the cricketer from one longitudinal player record.</p></div><div class="cam-hero-actions"><button class="secondary" data-cam-tab="players">Manage Players</button><button class="primary" data-go-route="upload">＋ Add Player Video</button></div></section>
    <section class="cam-stats">${metric('Players',players.length,'Real CrickAnalysis player profiles','green')}${metric('Players with analysis',withAnalysis,'Have completed development evidence','blue')}${metric('Completed analyses',Number(d.completed_count||0),'Existing video-analysis history','amber')}${metric('Coaches / Batches','Setup','Operational records not configured yet','gray')}</section>
    <section class="cam-dashboard-grid"><article class="panel cam-operations"><div class="panel-head"><div><h2>Academy Operations</h2><p>Management modules connected directly to player development.</p></div><span class="cam-badge">PHASE 1</span></div><div class="cam-module-grid">
    ${moduleCard('♙','Players','Enrollment, guardian/contact, profile and development history.','players',`${players.length} live`)}
    ${moduleCard('▦','Batches & Sessions','Training groups, schedules, capacity and session plans.','batches')}
    ${moduleCard('◇','Coaches','Coach profiles, assignments, workload and specialties.','coaches')}
    ${moduleCard('✓','Attendance','Player and coach attendance linked to each session.','attendance')}
    ${moduleCard('⚔','Teams & Matches','Squads, fixtures, selection and match linkage.','teams')}
    ${moduleCard('♜','Tournaments','Competition calendar, entries and academy squads.','tournaments')}
    ${moduleCard('$','Fees & Payments','Plans, invoices, payment status and receipts.','fees')}
    ${moduleCard('✦','Player Development','Video, biomechanics, coaching notes and progress evidence.','players','Core differentiator')}
    </div></article><aside class="cam-side-stack"><article class="panel cam-principle"><span class="cam-kicker">PRODUCT PRINCIPLE</span><h2>One player. One history.</h2><p>Attendance, payments, coaching notes, matches, videos and biomechanics attach to the same player profile.</p><div class="cam-flow"><span>Academy</span><b>＋</b><span>Coaching</span><b>＋</b><span>Analysis</span><b>=</b><span>Development proof</span></div></article><article class="panel cam-today"><div class="panel-head"><div><h2>Academy Today</h2><p>Operational scheduling will appear here as sessions are connected.</p></div></div><div class="cam-empty compact"><strong>No sessions configured</strong><span>Next implementation slice: Players → Batches → Coaches → Sessions/Attendance.</span></div></article></aside></section>`;
  }

  function content(tab,data){
    if(tab==='overview') return overview(data);
    if(tab==='players') return `<section class="cam-section-head"><div><span class="cam-kicker">UNIFIED PLAYER DIRECTORY</span><h1>Academy Players</h1><p>Existing CrickAnalysis players become the academy enrollment and development record.</p></div><button class="primary" data-go-route="upload">＋ Add Player Video</button></section><article class="panel cam-player-panel"><div class="panel-head"><div><h2>Player Records</h2><p>These counts come from the current CrickAnalysis data store.</p></div><span>${(data.players||[]).length}</span></div><div class="cam-player-list">${playerRows(data.players||[])}</div></article>`;
    if(tab==='batches') return foundation('Batches & Sessions','Create recurring training batches, assign players/coaches, manage capacity and attach a session plan to each practice.',['Batch name','Age / skill level','Days & time','Coach assignment','Capacity','Session plan','Ground / lane']);
    if(tab==='coaches') return foundation('Coaches','Manage coaching staff and connect assignments to the players and sessions they actually work with.',['Coach profile','Specialties','Availability','Batch assignments','Player assignments','Workload','Coach notes']);
    if(tab==='attendance') return foundation('Attendance','Capture attendance at session level so consistency can later be compared with development outcomes.',['Session roster','Present / absent / late','Coach attendance','Reason / note','Attendance %','Player trend','Batch trend']);
    if(tab==='teams') return foundation('Teams & Matches','Build academy squads, fixtures and selections while linking match footage and analysis back to each player.',['Team / age group','Squad','Fixture','Opponent','Venue','Selection','Score / result','Match video']);
    if(tab==='tournaments') return foundation('Tournaments','Track competitions, academy entries, squads, fixtures and development evidence from tournament play.',['Tournament','Dates','Teams entered','Squads','Fixtures','Results','Fees / logistics']);
    if(tab==='fees') return foundation('Fees & Payments','Provide the business-office layer for training plans while keeping billing separate from coaching assessment.',['Fee plan','Billing cycle','Invoice','Paid / due','Discount / scholarship','Receipt','Outstanding balance']);
    return overview(data);
  }

  async function render(){
    ensureNav();
    const current=route();
    if(current.page!=='cam') return;
    const token=++renderToken;
    let data={dashboard:{},players:[]};
    try{
      const [dashboard,players]=await Promise.all([getJson('/api/dashboard'),getJson('/api/players')]);
      data={dashboard,players:Array.isArray(players)?players:[]};
    }catch(err){ console.warn('Academy data unavailable',err); }
    if(token!==renderToken || route().page!=='cam') return;
    const main=qs('.main'); if(!main) return;
    const topbar=qs('.topbar',main);
    qsa(':scope > *',main).forEach(child=>{if(child!==topbar) child.remove();});
    const wrap=document.createElement('div');
    wrap.id='camWorkspace';
    wrap.innerHTML=`${tabs(current.tab)}<div class="cam-content">${content(current.tab,data)}</div>`;
    main.appendChild(wrap);
    qsa('[data-cam-tab]',wrap).forEach(b=>b.onclick=()=>go(b.dataset.camTab));
    qsa('[data-go-route]',wrap).forEach(b=>b.onclick=()=>{location.hash=b.dataset.goRoute;});
    ensureNav();
  }

  const observer=new MutationObserver(()=>ensureNav());
  observer.observe(document.documentElement,{childList:true,subtree:true});
  window.addEventListener('hashchange',()=>{setTimeout(()=>{ensureNav();render();},0);});
  document.addEventListener('DOMContentLoaded',()=>{ensureNav();render();});
  ensureNav();
  render();
})();
