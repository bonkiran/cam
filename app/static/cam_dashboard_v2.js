(() => {
  const SESSION_KEY='cam-cam-session-v1';
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  let scheduled=false;
  let rendering=false;
  let cachedMe=null;
  let meLoaded=false;

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    return {page:page||'dashboard',tab:new URLSearchParams(query).get('tab')||'overview'};
  }
  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function money(cents){
    return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(Number(cents||0)/100);
  }
  function fmtDate(value){
    if(!value)return '—';
    const d=new Date(`${value}T12:00:00`);
    return Number.isNaN(d.getTime())?value:d.toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric'});
  }
  function fmtTime(value){
    if(!value)return 'Time TBD';
    const [hh,mm]=String(value).split(':').map(Number);
    if(Number.isNaN(hh)||Number.isNaN(mm))return value;
    const d=new Date();d.setHours(hh,mm,0,0);
    return d.toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
  }
  async function json(url,options={}){
    const response=await fetch(url,{cache:'no-store',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    let data=null;try{data=await response.json();}catch{}
    if(!response.ok)throw new Error(data?.detail||`Request failed (${response.status})`);
    return data;
  }
  async function authMe(){
    if(meLoaded)return cachedMe;
    meLoaded=true;
    const token=sessionStorage.getItem(SESSION_KEY)||'';
    if(!token)return null;
    try{
      const response=await fetch('/api/auth/me',{cache:'no-store',headers:{Authorization:`Bearer ${token}`}});
      if(response.ok)cachedMe=await response.json();
    }catch{}
    return cachedMe;
  }
  function go(tab){location.hash=tab==='overview'?'cam':`academy?tab=${encodeURIComponent(tab)}`;}

  function metric(label,value,note,kind='green'){
    const icon=kind==='green'?'♙':kind==='blue'?'$':kind==='amber'?'◷':'▦';
    return `<article class="cam-stat ${kind}"><div class="cam-stat-icon">${icon}</div><div><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></div></article>`;
  }
  function sessionRow(session){
    return `<div class="cam-dash-session"><div><strong>${esc(fmtTime(session.start_time))} · ${esc(session.batch_name||'1-to-1 Session')}</strong><small>${esc(session.coach_name||'Coach not assigned')} · ${esc(session.location||'Location not set')}${session.resource?` · ${esc(session.resource)}`:''}</small></div><span>${Number(session.player_count||0)} player${Number(session.player_count||0)===1?'':'s'}</span></div>`;
  }
  function sessionsPanel(data){
    const groups=data.today_sessions?.group||[];
    const privateSessions=data.today_sessions?.private||[];
    return `<article class="panel cam-dash-panel"><div class="panel-head"><div><h2>Today's Sessions</h2><p>Group practices and 1-to-1 coaching scheduled for today.</p></div><button class="secondary" data-dashboard-go="batches">Manage Sessions</button></div>
      <div class="cam-dash-session-block"><h3>Group Sessions <span>${groups.length}</span></h3>${groups.length?groups.map(sessionRow).join(''):'<div class="cam-dash-empty">No group sessions scheduled today.</div>'}</div>
      <div class="cam-dash-session-block"><h3>1-to-1 Sessions <span>${privateSessions.length}</span></h3>${privateSessions.length?privateSessions.map(sessionRow).join(''):'<div class="cam-dash-empty">No 1-to-1 sessions scheduled today.</div>'}</div>
    </article>`;
  }
  function attendancePanel(data){
    const attendance=data.yesterday_attendance||{sessions:[]};
    const sessions=attendance.sessions||[];
    const rows=sessions.map(s=>`<div class="cam-dash-attendance"><div><strong>${esc(s.label)} · ${esc(fmtTime(s.start_time))}</strong><small>${esc(s.coach_name||'Coach not assigned')} · Coach: ${esc(s.coach_status||'not recorded')}</small></div><div class="cam-dash-attendance-counts"><span class="good">${Number(s.present||0)} present</span><span>${Number(s.late||0)} late</span><span class="bad">${Number(s.absent||0)} absent</span><span>${Number(s.excused||0)} excused</span>${Number(s.not_recorded||0)?`<span class="warn">${Number(s.not_recorded)} not recorded</span>`:''}</div></div>`).join('');
    return `<article class="panel cam-dash-panel"><div class="panel-head"><div><h2>Yesterday's Attendance</h2><p>${esc(fmtDate(attendance.date))} · quick completion check for coaches and players.</p></div><button class="secondary" data-dashboard-go="attendance">Open Attendance</button></div>${rows||'<div class="cam-dash-empty">No sessions were scheduled yesterday.</div>'}<div class="cam-dash-mobile-note">Mobile direction: coaches will be able to record Present, Late, Absent/No-show and attendance corrections from session view.</div></article>`;
  }
  function weatherHtml(weather){
    if(!weather?.configured)return `<div class="cam-dash-weather-state"><strong>Weekend weather</strong><span>Weather.com connection is ready for a server API key.</span></div>`;
    if(weather.status!=='ok')return `<div class="cam-dash-weather-state"><strong>Weekend weather</strong><span>${weather.status==='location_required'?'Add academy ZIP/country to load weather.':'Weather.com forecast is temporarily unavailable.'}</span></div>`;
    return `<div class="cam-dash-weather-days">${(weather.days||[]).map(day=>`<div><strong>${esc(day.day_of_week||fmtDate(day.date))}</strong><span>${day.high_f??'—'}° / ${day.low_f??'—'}°</span><small>${esc(day.narrative||'Forecast available')}</small></div>`).join('')}</div>`;
  }
  function matchRow(match){
    return `<div class="cam-dash-match"><div><span class="cam-dash-date">${esc(fmtDate(match.match_date))}</span><strong>${esc(match.team_name)} vs ${esc(match.opponent)}</strong><small>${esc(fmtTime(match.start_time))} · ${esc(match.venue||'Venue TBD')}${match.competition?` · ${esc(match.competition)}`:''}</small></div><div class="cam-dash-confirmations"><span class="good">${Number(match.confirmed||0)} confirmed</span><span class="warn">${Number(match.awaiting||0)} awaiting</span>${Number(match.declined||0)?`<span class="bad">${Number(match.declined)} declined</span>`:''}<small>${Number(match.squad_count||0)} selected</small></div></div>`;
  }
  function eventsPanel(data){
    const camName=data.academy?.name||'Academy';
    const matches=data.upcoming_matches||[];
    return `<article class="panel cam-dash-panel cam-dash-events"><div class="panel-head"><div><h2>Upcoming Events for ${esc(camName)}</h2><p>Matches in the next 7 days, player confirmations and weekend weather.</p></div><button class="secondary" data-dashboard-go="teams">Teams & Matches</button></div><div class="cam-dash-events-grid"><div class="cam-dash-matches"><h3>Matches This Week / Weekend</h3>${matches.length?matches.map(matchRow).join(''):'<div class="cam-dash-empty">No scheduled matches in the next 7 days.</div>'}</div><aside class="cam-dash-weather"><h3>Weekend Weather</h3>${weatherHtml(data.weather)}</aside></div></article>`;
  }

  function dashboardHtml(data){
    const m=data.metrics||{};
    const camName=data.academy?.name||'Academy';
    const person=data.user?.display_name||'Academy Admin';
    const pending=Number(m.fee_pending_cents||0),late=Number(m.fee_late_cents||0);
    return `<section class="cam-hero cam-dashboard-welcome"><div><span class="cam-kicker">ACADEMY OPERATIONS DASHBOARD</span><h1>Welcome, ${esc(person)}</h1><p>${esc(camName)} · ${esc(fmtDate(data.as_of))}</p></div><div class="cam-hero-actions"><button class="secondary" data-dashboard-go="batches">Sessions</button><button class="secondary" data-dashboard-go="fees">Fees & Payments</button><button class="primary" data-dashboard-go="players">Manage Players</button></div></section>
      <section class="cam-stats">${metric('Players',Number(m.players||0),'Active academy directory','green')}${metric('Fee received',money(m.fee_received_mtd_cents),'Month to date','blue')}${metric('Fee Pending / Late',money(pending+late),`${money(pending)} pending · ${money(late)} late`,'amber')}${metric("Today's Sessions",Number(m.today_session_count||0),'Group + 1-to-1','gray')}</section>
      <section class="cam-dashboard-v2-grid">${eventsPanel(data)}${sessionsPanel(data)}${attendancePanel(data)}</section>`;
  }

  async function normalizeTabsAndSetup(){
    const r=route();if(r.page!=='cam')return;
    const tabs=$('#camWorkspace .cam-tabs');
    const overview=tabs?.querySelector('[data-cam-tab="overview"]');
    if(overview)overview.textContent='Dashboard';
    const me=await authMe();
    const setup=tabs?.querySelector('[data-cam-tab="setup"]');
    if(setup&&me&&!['owner','admin'].includes(String(me.role)))setup.remove();
    if(r.tab==='setup'){
      if(me&&!['owner','admin'].includes(String(me.role))){go('overview');return;}
      const timezone=$('#camProfileForm [name="timezone"]');
      if(timezone){
        const label=timezone.closest('label');
        if(label)label.style.display='none';
      }
    }
  }

  async function renderDashboard(){
    const r=route();
    if(r.page!=='cam'||r.tab!=='overview'||rendering)return;
    const content=$('#camWorkspace .cam-content');
    if(!content||content.dataset.dashboardV2==='1'||content.dataset.dashboardV2==='loading')return;
    rendering=true;content.dataset.dashboardV2='loading';
    try{
      const data=await json('/api/cam/dashboard/operations');
      if(route().page!=='cam'||route().tab!=='overview')return;
      content.innerHTML=dashboardHtml(data);
      content.dataset.dashboardV2='1';
      $$('[data-dashboard-go]',content).forEach(button=>button.onclick=()=>go(button.dataset.dashboardGo));
    }catch(error){
      content.innerHTML=`<div class="warning">Dashboard could not load: ${esc(error.message)}</div>`;
      content.dataset.dashboardV2='1';
    }finally{rendering=false;}
  }

  async function apply(){
    scheduled=false;
    if(route().page!=='cam')return;
    await normalizeTabsAndSetup();
    await renderDashboard();
  }
  function schedule(){if(scheduled)return;scheduled=true;setTimeout(apply,20);}

  window.addEventListener('hashchange',()=>{meLoaded=false;cachedMe=null;schedule();});
  window.addEventListener('cam-payments-updated',schedule);
  document.addEventListener('DOMContentLoaded',schedule);
  new MutationObserver(()=>{if(route().page==='cam')schedule();}).observe(document.documentElement,{childList:true,subtree:true});
  schedule();
})();