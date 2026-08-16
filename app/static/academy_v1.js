(() => {
  const qs = (s, root=document) => root.querySelector(s);
  const qsa = (s, root=document) => [...root.querySelectorAll(s)];
  let renderTimer = null;

  const tabs = [
    ['overview','Overview'],
    ['players','Players'],
    ['batches','Batches & Sessions'],
    ['coaches','Coaches'],
    ['attendance','Attendance'],
    ['teams','Teams & Matches'],
    ['tournaments','Tournaments'],
    ['fees','Fees & Payments'],
  ];

  function academyRoute(){
    const raw = location.hash.replace(/^#/, '');
    const [page, query=''] = raw.split('?');
    const params = new URLSearchParams(query);
    return {page, tab: params.get('tab') || 'overview'};
  }

  function go(tab='overview'){
    location.hash = tab === 'overview' ? 'academy' : `academy?tab=${encodeURIComponent(tab)}`;
  }

  async function getJson(url){
    const response = await fetch(url, {cache:'no-store'});
    if(!response.ok) throw new Error(`Request failed (${response.status})`);
    return response.json();
  }

  function ensureAcademyNav(){
    const nav = qs('.sidebar .nav');
    if(!nav || qs('[data-route="academy"]', nav)) return;
    const players = qs('[data-route="players"]', nav);
    const button = document.createElement('button');
    button.dataset.route = 'academy';
    button.className = academyRoute().page === 'academy' ? 'active' : '';
    button.innerHTML = '<i>⌂</i><b>Academy</b>';
    button.title = 'Academy';
    button.onclick = () => go('overview');
    if(players) players.insertAdjacentElement('afterend', button);
    else nav.appendChild(button);
  }

  function tabBar(active){
    return `<div class="academy-tabs">${tabs.map(([id,label]) =>
      `<button class="${active===id?'active':''}" data-academy-tab="${id}">${label}</button>`
    ).join('')}</div>`;
  }

  function metric(label, value, note, kind='green'){
    return `<article class="academy-stat ${kind}"><div class="academy-stat-icon">${kind==='green'?'♙':kind==='blue'?'▦':kind==='amber'?'◷':'◎'}</div><div><span>${label}</span><strong>${value}</strong><small>${note}</small></div></article>`;
  }

  function moduleCard(icon, title, text, tab, meta='Foundation'){
    return `<button class="academy-module" data-academy-tab="${tab}">
      <span class="academy-module-icon">${icon}</span>
      <span class="academy-module-copy"><strong>${title}</strong><small>${text}</small></span>
      <span class="academy-module-meta">${meta}</span><b>→</b>
    </button>`;
  }

  function emptyOperational(title, description, fields){
    return `<section class="academy-two-col">
      <article class="panel academy-foundation-card">
        <div class="academy-kicker">ACADEMY OPERATIONS · FOUNDATION</div>
        <h2>${title}</h2>
        <p>${description}</p>
        <div class="academy-field-list">${fields.map(x=>`<span>${x}</span>`).join('')}</div>
        <div class="academy-foundation-note"><strong>No fabricated academy data.</strong> This screen is injected now as the product foundation; persistence/workflows will be connected module-by-module.</div>
      </article>
      <article class="panel academy-link-card">
        <div class="academy-kicker">CONNECTED PLAYER DEVELOPMENT</div>
        <h2>Use the same player record</h2>
        <p>Academy operations will attach to the existing CrickAnalysis player, video, event and biomechanics history instead of creating a second player identity.</p>
        <div class="academy-journey">
          <span>Enrollment</span><i>→</i><span>Session</span><i>→</i><span>Coach feedback</span><i>→</i><span>Video evidence</span><i>→</i><span>Progress</span>
        </div>
      </article>
    </section>`;
  }

  function playerRows(players){
    if(!players.length) return `<div class="academy-empty"><strong>No academy players yet</strong><span>Upload footage with a player name to create the first unified player profile.</span></div>`;
    return players.map(p => `<div class="academy-player-row" data-search="${String(p.name||'').toLowerCase()}">
      <div class="academy-avatar">${String(p.name||'?').split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase()}</div>
      <div><strong>${p.name}</strong><small>${p.video_count || 0} video(s) · ${p.completed_analyses || 0} completed analysis(es)</small></div>
      <span class="academy-status">Unified profile</span>
      <button data-open-player-analyses="${encodeURIComponent(p.name || '')}">View development →</button>
    </div>`).join('');
  }

  function overview(data){
    const players = data.players || [];
    const dashboard = data.dashboard || {};
    const developed = players.filter(p => Number(p.completed_analyses || 0) > 0).length;
    const completed = Number(dashboard.completed_count || 0);
    return `
      <section class="academy-hero">
        <div><span class="academy-kicker">ACADEMY + PERFORMANCE INTELLIGENCE</span><h1>Academy Dashboard</h1><p>Run the academy and develop the cricketer from one longitudinal player record.</p></div>
        <div class="academy-hero-actions"><button class="secondary" data-academy-tab="players">Manage Players</button><button class="primary" data-go-route="upload">＋ Add Player Video</button></div>
      </section>
      <section class="academy-stats">
        ${metric('Players', players.length, 'Real CrickAnalysis player profiles', 'green')}
        ${metric('Players with analysis', developed, 'Have completed development evidence', 'blue')}
        ${metric('Completed analyses', completed, 'Existing video-analysis history', 'amber')}
        ${metric('Coaches / Batches', 'Setup', 'Operational records not configured yet', 'gray')}
      </section>
      <section class="academy-dashboard-grid">
        <article class="panel academy-operations">
          <div class="panel-head"><div><h2>Academy Operations</h2><p>Management modules inspired by real academy workflows, without separating them from player development.</p></div><span class="academy-badge">PHASE 1</span></div>
          <div class="academy-module-grid">
            ${moduleCard('♙','Players','Enrollment, profile, guardian/contact and development history.','players',`${players.length} live`)}
            ${moduleCard('▦','Batches & Sessions','Training groups, schedule, capacity and session plans.','batches')}
            ${moduleCard('◇','Coaches','Coach profiles, assignments, workload and specialties.','coaches')}
            ${moduleCard('✓','Attendance','Player and coach attendance linked to each session.','attendance')}
            ${moduleCard('⚔','Teams & Matches','Squads, fixtures, selection and match linkage.','teams')}
            ${moduleCard('♜','Tournaments','Competition calendar, entries and academy squads.','tournaments')}
            ${moduleCard('$','Fees & Payments','Plans, invoices, payment status and receipts.','fees')}
            ${moduleCard('✦','Player Development','Video, biomechanics, coaching notes and progress evidence.','players','Core differentiator')}
          </div>
        </article>
        <aside class="academy-side-stack">
          <article class="panel academy-principle">
            <span class="academy-kicker">PRODUCT PRINCIPLE</span>
            <h2>One player. One history.</h2>
            <p>Attendance, payments, coaching notes, matches, videos and biomechanics will attach to the same player profile.</p>
            <div class="academy-flow"><span>Academy</span><b>＋</b><span>Coaching</span><b>＋</b><span>Analysis</span><b>=</b><span>Development proof</span></div>
          </article>
          <article class="panel academy-today">
            <div class="panel-head"><div><h2>Academy Today</h2><p>Operational scheduling will appear here as sessions are connected.</p></div></div>
            <div class="academy-empty compact"><strong>No sessions configured</strong><span>Next implementation slice: Players → Batches → Coaches → Sessions/Attendance.</span></div>
          </article>
        </aside>
      </section>`;
  }

  function playersTab(players){
    return `<section class="academy-section-head"><div><span class="academy-kicker">UNIFIED PLAYER DIRECTORY</span><h1>Academy Players</h1><p>Existing CrickAnalysis players are the starting point for academy enrollment and development history.</p></div><button class="primary" data-go-route="upload">＋ Add Player Video</button></section>
      <article class="panel academy-player-panel"><div class="panel-head"><div><h2>Player Records</h2><p>These counts come from the current CrickAnalysis data store.</p></div><span>${players.length}</span></div><div class="academy-player-list">${playerRows(players)}</div></article>`;
  }

  function tabContent(tab, data){
    if(tab === 'overview') return overview(data);
    if(tab === 'players') return playersTab(data.players || []);
    if(tab === 'batches') return emptyOperational('Batches & Sessions','Create recurring training batches, assign players/coaches, manage capacity and attach a session plan to each practice.',['Batch name','Age / skill level','Days & time','Coach assignment','Capacity','Session plan','Ground / lane']);
    if(tab === 'coaches') return emptyOperational('Coaches','Manage coaching staff and connect every coach assignment to the players and sessions they actually work with.',['Coach profile','Specialties','Availability','Batch assignments','Player assignments','Workload','Coach notes']);
    if(tab === 'attendance') return emptyOperational('Attendance','Capture attendance at the session level so consistency can later be compared with player-development outcomes.',['Session roster','Present / absent / late','Coach attendance','Reason / note','Attendance %','Player trend','Batch trend']);
    if(tab === 'teams') return emptyOperational('Teams & Matches','Build academy squads, fixtures and selections while linking match footage and analysis back to each player.',['Team / age group','Squad','Fixture','Opponent','Venue','Selection','Score / result','Match video']);
    if(tab === 'tournaments') return emptyOperational('Tournaments','Track competitions, academy entries, squads, fixtures and player-development evidence from tournament play.',['Tournament','Dates','Teams entered','Squads','Fixtures','Results','Fees / logistics']);
    if(tab === 'fees') return emptyOperational('Fees & Payments','Provide the business-office layer for membership/training plans while preserving a clean separation from coaching assessments.',['Fee plan','Billing cycle','Invoice','Paid / due','Discount / scholarship','Receipt','Outstanding balance']);
    return overview(data);
  }

  async function renderAcademy(){
    const {page, tab} = academyRoute();
    ensureAcademyNav();
    qsa('.sidebar .nav button').forEach(b=>b.classList.toggle('active', b.dataset.route === 'academy' && page === 'academy'));
    if(page !== 'academy') return;

    const main = qs('.main');
    if(!main) return;
    let data = {dashboard:{}, players:[]};
    try{
      const [dashboard, players] = await Promise.all([getJson('/api/dashboard'), getJson('/api/players')]);
      data = {dashboard, players:Array.isArray(players)?players:[]};
    }catch(error){
      console.warn('Academy dashboard data unavailable', error);
    }
    if(academyRoute().page !== 'academy') return;

    const topbar = qs('.topbar', main);
    qsa(':scope > *', main).forEach(child=>{ if(child !== topbar) child.remove(); });
    const wrapper = document.createElement('div');
    wrapper.id = 'academyWorkspace';
    wrapper.innerHTML = `${tabBar(tab)}<div class="academy-content">${tabContent(tab, data)}</div>`;
    main.appendChild(wrapper);

    qsa('[data-academy-tab]', wrapper).forEach(btn=>btn.onclick=()=>go(btn.dataset.academyTab));
    qsa('[data-go-route]', wrapper).forEach(btn=>btn.onclick=()=>{location.hash=btn.dataset.goRoute});
    qsa('[data-open-player-analyses]', wrapper).forEach(btn=>btn.onclick=()=>{location.hash='analyses'});
  }

  function schedule(){
    clearTimeout(renderTimer);
    renderTimer = setTimeout(()=>{
      ensureAcademyNav();
      renderAcademy();
    }, 90);
  }

  const observer = new MutationObserver(schedule);
  observer.observe(document.documentElement, {childList:true, subtree:true});
  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  schedule();
})();
