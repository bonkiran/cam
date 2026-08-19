(() => {
  const SESSION_KEY='cam-academy-session-v1';
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  const OWNER_ROLES=new Set(['owner','admin']);
  const TOP_TABS=[
    ['overview','Dashboard'],
    ['players','Players'],
    ['programs','Programs'],
    ['coaches','Coaches'],
    ['fees','Finance'],
    ['reports','Reports'],
    ['settings','Settings'],
  ];
  const TOP_FOR_ROUTE={
    overview:'overview',players:'players',player360:'players',reviews:'players',
    programs:'programs',batches:'programs',teams:'programs',tournaments:'programs',
    coaches:'coaches',attendance:'players',fees:'fees',reports:'reports',
    settings:'settings',setup:'settings',access:'settings',parent:'settings',
  };
  let scheduled=false;
  let applying=false;
  let rerunRequested=false;
  let meLoaded=false;
  let cachedMe=null;
  let dashboardCache=null;
  let dashboardCacheAt=0;

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    const params=new URLSearchParams(query);
    return {page:page||'dashboard',tab:params.get('tab')||'overview',params};
  }
  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function notify(message){
    if(typeof window.toast==='function')window.toast(message);else console.log(message);
  }
  async function api(url,options={}){
    const response=await fetch(url,{cache:'no-store',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    let data=null;try{data=await response.json();}catch{}
    if(!response.ok)throw new Error(data?.detail||`Request failed (${response.status})`);
    return data;
  }
  async function authMe(){
    const token=sessionStorage.getItem(SESSION_KEY)||'';
    if(!token){meLoaded=false;cachedMe=null;return null;}
    if(meLoaded&&cachedMe)return cachedMe;
    try{
      const response=await fetch('/api/auth/me',{cache:'no-store',headers:{Authorization:`Bearer ${token}`}});
      if(response.ok){cachedMe=await response.json();meLoaded=true;return cachedMe;}
    }catch{}
    meLoaded=false;cachedMe=null;return null;
  }
  function isOwner(me){return !!me&&OWNER_ROLES.has(String(me.role||'').toLowerCase());}
  function go(tab,params={}){
    const query=new URLSearchParams({tab,...params});
    location.hash=tab==='overview'?'academy':`academy?${query.toString()}`;
  }
  function goExternal(hash){location.hash=hash.replace(/^#/,'');}

  function resetOwnerTabs(){
    const tabs=$('#academyWorkspace .academy-tabs');
    if(!tabs)return;
    $$('[data-owner-console-tab]',tabs).forEach(button=>button.remove());
    $$('button',tabs).forEach(button=>{button.hidden=false;button.classList.remove('academy-owner-legacy-tab');});
  }
  function normalizeOwnerTabs(){
    const info=route();
    const tabs=$('#academyWorkspace .academy-tabs');
    if(!tabs)return;
    $$('button',tabs).forEach(button=>{
      if(button.dataset.ownerConsoleTab)return;
      button.hidden=true;
      button.classList.add('academy-owner-legacy-tab');
    });
    const activeTop=TOP_FOR_ROUTE[info.tab]||'overview';
    TOP_TABS.forEach(([tab,label])=>{
      let button=tabs.querySelector(`[data-owner-console-tab="${tab}"]`);
      if(!button){
        button=document.createElement('button');
        button.type='button';
        button.dataset.ownerConsoleTab=tab;
        button.dataset.academyTab=tab;
        button.className='academy-owner-console-tab';
        button.onclick=()=>go(tab);
        tabs.appendChild(button);
      }
      button.textContent=label;
      button.hidden=false;
      button.classList.toggle('active',activeTop===tab);
      button.setAttribute('aria-current',activeTop===tab?'page':'false');
    });
  }

  function contextNav(items,active){
    return `<nav class="academy-owner-context-nav" aria-label="Academy workspace sections">${items.map(([id,label,tab,params={}])=>`<button type="button" class="${id===active?'active':''}" data-owner-context-tab="${esc(tab)}" data-owner-context-params="${esc(JSON.stringify(params))}">${esc(label)}</button>`).join('')}</nav>`;
  }
  function wireContextNav(root=document){
    $$('[data-owner-context-tab]',root).forEach(button=>{
      if(button.dataset.ownerContextWired==='1')return;
      button.dataset.ownerContextWired='1';
      button.onclick=()=>{
        let params={};try{params=JSON.parse(button.dataset.ownerContextParams||'{}');}catch{}
        go(button.dataset.ownerContextTab,params);
      };
    });
  }
  function addProgramsContext(){
    const info=route();
    if(!['programs','batches','teams','tournaments'].includes(info.tab))return;
    const content=$('#academyWorkspace .academy-content');if(!content||$('.academy-owner-context-nav',content))return;
    const html=contextNav([
      ['programs','Programs & Enrollment','programs'],
      ['batches','Batches & Sessions','batches'],
      ['teams','Matches','teams'],
      ['tournaments','Tournaments','tournaments'],
    ],info.tab);
    content.insertAdjacentHTML('afterbegin',html);
    wireContextNav(content);
  }

  function settingsHtml(){
    const cards=[
      ['academy-profile','Academy Profile','Organization, primary location and academy contact information.','setup','⚙'],
      ['access','Access & Roles','Owner/Admin account access, role assignments and security audit trail.','access','⌘'],
      ['fees','Fee Setup','Fee plans, billing rules, invoices and payment setup.','fees','$'],
      ['integrations','Integrations','CricClubs, weather, WhatsApp, push, payments, Jira and future adapters.','integrations','↔'],
    ];
    return `<section class="academy-owner-settings-shell"><section class="academy-section-head"><div><span class="academy-kicker">OWNER / ADMIN</span><h1>Settings</h1><p>Configuration is kept out of daily academy operations and grouped here for authorized administrators.</p></div></section><div class="academy-owner-settings-grid">${cards.map(([id,title,text,target,icon])=>`<button type="button" class="panel academy-owner-settings-card" data-owner-settings-target="${esc(target)}"><span>${icon}</span><div><strong>${esc(title)}</strong><small>${esc(text)}</small></div><b>→</b></button>`).join('')}</div><article class="panel academy-owner-integration-note"><div><h2>Integration architecture remains intact</h2><p>Academy pages call provider adapters. Track B.0 will make each provider configuration academy-specific without changing this navigation model.</p></div><span>SAAS READY SHELL</span></article></section>`;
  }
  function renderSettings(){
    const info=route();if(info.tab!=='settings')return;
    const content=$('#academyWorkspace .academy-content');if(!content)return;
    if(!$('.academy-owner-settings-shell',content))content.innerHTML=settingsHtml();
    $$('[data-owner-settings-target]',content).forEach(button=>{
      if(button.dataset.ownerSettingsWired==='1')return;
      button.dataset.ownerSettingsWired='1';
      button.onclick=()=>{
        const target=button.dataset.ownerSettingsTarget;
        if(target==='integrations')goExternal('integrations');else go(target);
      };
    });
  }

  function textLine(label,value){return `<div class="academy-owner-detail-line"><span>${esc(label)}</span><strong>${esc(value||'—')}</strong></div>`;}
  function guardianCard(g){
    const flags=[g.is_primary?'Primary':'',g.billing_contact?'Billing':'',g.pickup_authorized?'Pickup':''].filter(Boolean).join(' · ');
    return `<div class="academy-owner-person-card"><strong>${esc(`${g.first_name||''} ${g.last_name||''}`.trim()||'Guardian')}</strong><small>${esc(g.relationship||'Parent / Guardian')}${flags?` · ${esc(flags)}`:''}</small><span>${esc(g.phone||'No phone')}</span><span>${esc(g.email||'No email')}</span></div>`;
  }
  function player360Html(data){
    const p=data.player||{};
    const guardians=data.guardians||[];
    const batches=data.batches||[];
    const coaches=data.coaches||[];
    const att=data.attendance||{};
    const fullName=p.name||[p.first_name,p.last_name].filter(Boolean).join(' ')||'Player';
    return `<section class="academy-owner-player360"><section class="academy-section-head academy-owner-player360-head"><div><span class="academy-kicker">PLAYER 360</span><h1>${esc(fullName)}</h1><p>One operational record for player, family, coaching, attendance, academy assignments and connected cricket data.</p></div><div class="academy-owner-head-actions"><button class="secondary" data-owner-player-action="directory">← Player Directory</button><button class="primary" data-owner-player-action="edit">Edit Player</button></div></section><section class="academy-owner-player-summary"><article><span>Status</span><strong>${esc(p.status||'active')}</strong></article><article><span>Joined</span><strong>${esc(p.joined_on||'—')}</strong></article><article><span>Current Batches</span><strong>${batches.length}</strong></article><article><span>Coach Reviews</span><strong>${Number(data.review_count||0)}</strong></article></section><section class="academy-owner-player-grid"><article class="panel"><div class="panel-head"><div><h2>Player Bio</h2><p>Core identity, cricket and emergency information.</p></div></div>${textLine('Preferred name',p.preferred_name)}${textLine('Date of birth',p.date_of_birth)}${textLine('Skill level',p.skill_level)}${textLine('Batting',p.batting_style)}${textLine('Bowling',p.bowling_style)}${textLine('Handedness',p.handedness)}${textLine('Phone',p.phone)}${textLine('Email',p.email)}${textLine('Emergency contact',p.emergency_contact_name)}${textLine('Emergency phone',p.emergency_contact_phone)}</article><article class="panel"><div class="panel-head"><div><h2>Parents & Guardians</h2><p>Family, billing and pickup contacts.</p></div></div><div class="academy-owner-person-list">${guardians.length?guardians.map(guardianCard).join(''):'<div class="academy-dash-empty">No guardian records.</div>'}</div></article><article class="panel"><div class="panel-head"><div><h2>Academy Assignments</h2><p>Current programs, batches and coaching relationships.</p></div></div><div class="academy-owner-assignment-list">${batches.length?batches.map(b=>`<div><strong>${esc(b.batch_name)}</strong><small>${esc(b.program_name||'No program')} · ${esc(b.status||'active')}</small></div>`).join(''):'<div class="academy-dash-empty">No current batch assignment.</div>'}</div><div class="academy-owner-assignment-list">${coaches.length?coaches.map(c=>`<div><strong>${esc(`${c.first_name||''} ${c.last_name||''}`.trim())}</strong><small>${esc(c.assignment_role||'coach')} · since ${esc(c.start_date||'not set')}</small></div>`).join(''):'<div class="academy-dash-empty">No active player coach assignment.</div>'}</div></article><article class="panel"><div class="panel-head"><div><h2>Attendance</h2><p>Recorded player attendance history.</p></div><button class="secondary" data-owner-player-action="attendance">Open Attendance</button></div><div class="academy-owner-attendance-grid"><span><b>${Number(att.present||0)}</b>Present</span><span><b>${Number(att.late||0)}</b>Late</span><span><b>${Number(att.absent||0)}</b>No-show</span><span><b>${Number(att.excused||0)}</b>Excused</span></div></article><article class="panel"><div class="panel-head"><div><h2>CricClubs Profile</h2><p>External player identity stays adapter-based for SaaS compatibility.</p></div></div><div class="academy-owner-integration-state"><strong>${data.cricclubs?.status==='connected'?'Connected':'Not connected'}</strong><span>API access and credentials will be configured per academy in the integration layer.</span></div></article><article class="panel"><div class="panel-head"><div><h2>Reviews, Requests & Complaints</h2><p>Coach development history plus parent/guardian operational feedback.</p></div><button class="secondary" data-owner-player-action="reviews">Coach Reviews</button></div><div class="academy-owner-request-state"><span>Coach reviews</span><strong>${Number(data.review_count||0)}</strong></div><div class="academy-owner-request-state"><span>Parent/Guardian requests & complaints</span><strong>${data.requests_complaints?.status==='not_configured'?'Workflow next':'0'}</strong></div></article></section></section>`;
  }
  async function renderPlayer360(){
    const info=route();if(info.tab!=='player360')return;
    const id=Number(info.params.get('player_id')||0);
    const content=$('#academyWorkspace .academy-content');if(!content)return;
    if(!id){content.innerHTML='<div class="warning">Select a player from the Player Directory.</div>';return;}
    if(content.dataset.ownerPlayer360===String(id))return;
    content.dataset.ownerPlayer360=String(id);
    content.innerHTML='<div class="academy-loading">Loading Player 360…</div>';
    try{
      const data=await api(`/api/academy/owner-console/players/${id}/summary`);
      if(route().tab!=='player360'||Number(route().params.get('player_id'))!==id)return;
      content.innerHTML=player360Html(data);
      $$('[data-owner-player-action]',content).forEach(button=>{
        button.onclick=()=>{
          const action=button.dataset.ownerPlayerAction;
          if(action==='directory'||action==='edit')go('players',action==='edit'?{edit_player:String(id)}:{});
          if(action==='attendance')go('attendance',{player_id:String(id)});
          if(action==='reviews')go('reviews',{player_id:String(id)});
        };
      });
    }catch(error){content.innerHTML=`<div class="warning">Player 360 could not load: ${esc(error.message)}</div>`;}
  }

  async function enhancePlayerDirectory(){
    const info=route();if(info.tab!=='players')return;
    const list=$('#academyWorkspace .academy-player-list');if(!list||list.dataset.ownerConsole==='1')return;
    list.dataset.ownerConsole='1';
    let directory=[];try{directory=await api('/api/academy/owner-console/players');}catch{}
    const byId=new Map(directory.map(p=>[String(p.id),p]));
    $$('.academy-player-row[data-player-id]',list).forEach(row=>{
      const id=String(row.dataset.playerId||'');
      const data=byId.get(id);
      const copy=row.children[1];
      if(copy&&data){
        const batchNames=(data.batches||[]).map(b=>b.name).filter(Boolean);
        const guardianNames=(data.guardians||[]).map(g=>g.name).filter(Boolean);
        const meta=document.createElement('small');
        meta.className='academy-owner-player-meta';
        meta.textContent=`Batches: ${batchNames.length?batchNames.join(', '):'Not assigned'} · Guardians: ${guardianNames.length?guardianNames.join(', '):'Not added'} · CricClubs: ${data.cricclubs?.status==='connected'?'Connected':'Not connected'}`;
        copy.appendChild(meta);
      }
      const actions=$('.academy-row-actions',row);
      if(actions&&!$('[data-owner-player360]',actions)){
        const button=document.createElement('button');button.type='button';button.dataset.ownerPlayer360=id;button.textContent='Player 360';
        button.onclick=()=>go('player360',{player_id:id});actions.prepend(button);
      }
    });
    const editPlayer=info.params.get('edit_player');
    if(editPlayer){
      const edit=$(`[data-edit-player="${CSS.escape(editPlayer)}"]`,list);if(edit)setTimeout(()=>edit.click(),0);
    }
  }

  function moneyUnavailable(label){return `<div class="academy-owner-money-card"><span>${esc(label)}</span><strong>—</strong><small>Finance ledger not enabled yet</small></div>`;}
  function dashboardSnapshotHtml(batches,players,asOf){
    const month=String(asOf||new Date().toISOString().slice(0,10)).slice(0,7);
    const registrations=players.filter(p=>String(p.joined_on||'').startsWith(month));
    const active=batches.filter(b=>String(b.status)==='active');
    return `<section id="academyOwnerSnapshot" class="academy-owner-dashboard-snapshot"><article class="panel"><div class="panel-head"><div><h2>Batch Breakdown</h2><p>Current active player count by batch.</p></div><button class="secondary" data-owner-snapshot-go="batches">Manage</button></div><div class="academy-owner-batch-breakdown">${active.length?active.map(b=>`<div><span>${esc(b.name)}</span><strong>${Number(b.active_player_count||0)}</strong><small>${Number(b.waitlist_count||0)} waitlisted · capacity ${Number(b.capacity||0)}</small></div>`).join(''):'<div class="academy-dash-empty">No active batches.</div>'}</div></article><article class="panel"><div class="panel-head"><div><h2>New Player Registrations</h2><p>${esc(month)} · current month.</p></div><button class="secondary" data-owner-snapshot-go="players">Players</button></div><strong class="academy-owner-registration-count">${registrations.length}</strong><div class="academy-owner-registration-list">${registrations.slice(0,5).map(p=>`<span>${esc(p.name)} <small>${esc(p.joined_on||'')}</small></span>`).join('')||'<span>No new registrations this month.</span>'}</div></article><article class="panel academy-owner-outgoings"><div class="panel-head"><div><h2>Current Month Academy Outgoings</h2><p>Coach salary, facility payments and operating expenses will be recorded in Finance.</p></div><button class="secondary" data-owner-snapshot-go="fees">Finance</button></div><div class="academy-owner-money-grid">${moneyUnavailable('Coach Salary Paid')}${moneyUnavailable('Facility Payments')}${moneyUnavailable('Academy Expenses')}</div></article></section>`;
  }

  async function dashboardData(){
    if(dashboardCache&&Date.now()-dashboardCacheAt<5000)return dashboardCache;
    dashboardCache=await api('/api/academy/dashboard/operations');dashboardCacheAt=Date.now();return dashboardCache;
  }
  async function enhanceDashboardSnapshot(){
    const info=route();if(info.tab!=='overview')return;
    const content=$('#academyWorkspace .academy-content');if(!content||$('#academyOwnerSnapshot',content))return;
    const stats=$('.academy-stats',content);if(!stats)return;
    try{
      const [batches,players,data]=await Promise.all([api('/api/academy/batches'),api('/api/academy/owner-console/players'),dashboardData()]);
      if(route().tab!=='overview'||$('#academyOwnerSnapshot',content))return;
      stats.insertAdjacentHTML('afterend',dashboardSnapshotHtml(batches,players,data.as_of));
      $$('[data-owner-snapshot-go]',content).forEach(button=>button.onclick=()=>go(button.dataset.ownerSnapshotGo));
    }catch{}
  }

  function channelsFromForm(form){return $$('input[name="notify_channel"]:checked',form).map(input=>input.value);}
  function notificationOptions(){return `<fieldset class="academy-owner-notify-options"><legend>Notify affected parties</legend><label><input type="checkbox" name="notify_channel" value="push" checked> Mobile push</label><label><input type="checkbox" name="notify_channel" value="whatsapp" checked> WhatsApp</label><small>CAM records the notification event and recipients now. External providers are not called until configured.</small></fieldset>`;}
  function closeDialog(){const dialog=$('#academyOwnerSessionDialog');if(dialog){try{dialog.close();}catch{}dialog.remove();}}
  function openDialog(html){
    closeDialog();
    const dialog=document.createElement('dialog');dialog.id='academyOwnerSessionDialog';dialog.className='academy-owner-dialog';dialog.innerHTML=html;document.body.appendChild(dialog);
    $('[data-owner-dialog-close]',dialog).onclick=closeDialog;
    if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
    return dialog;
  }
  async function queueSessionNotification(session,eventType,channels,message,metadata={}){
    if(!channels.length)return null;
    return api('/api/academy/owner-console/notification-events',{method:'POST',body:JSON.stringify({event_type:eventType,entity_type:'session',entity_id:Number(session.id),channels,message,metadata})});
  }
  function refreshDashboard(){
    dashboardCache=null;dashboardCacheAt=0;
    const content=$('#academyWorkspace .academy-content');
    if(content){delete content.dataset.dashboardV2;content.innerHTML='<div class="academy-loading">Refreshing dashboard…</div>';}
    window.dispatchEvent(new Event('academy-payments-updated'));
    schedule();
  }
  async function rescheduleSession(sessionId){
    let session;try{session=await api(`/api/academy/sessions/${sessionId}`);}catch(error){notify(error.message);return;}
    const dialog=openDialog(`<form method="dialog" id="academyOwnerRescheduleForm"><div class="academy-owner-dialog-head"><div><span>SESSION ACTION</span><h2>Reschedule Session</h2><p>${esc(session.batch_name||'1-to-1 Session')} · ${esc(session.session_date)} ${esc(session.start_time)}</p></div><button type="button" data-owner-dialog-close>×</button></div><div class="academy-form-grid two"><label class="academy-field"><span>New Date *</span><input name="session_date" type="date" value="${esc(session.session_date)}" required></label><label class="academy-field"><span>New Time *</span><input name="start_time" type="time" value="${esc(session.start_time)}" required></label></div>${notificationOptions()}<div class="academy-form-actions"><span id="academyOwnerActionStatus"></span><button type="submit" class="primary">Save Reschedule</button></div></form>`);
    const form=$('#academyOwnerRescheduleForm',dialog);
    form.onsubmit=async event=>{
      event.preventDefault();const button=form.querySelector('button[type="submit"]');button.disabled=true;
      try{
        const fd=new FormData(form);
        const before={session_date:session.session_date,start_time:session.start_time};
        const payload={session_date:String(fd.get('session_date')),start_time:String(fd.get('start_time')),duration_minutes:Number(session.duration_minutes),coach_id:session.coach_id?Number(session.coach_id):null,location:session.location||null,resource:session.resource||null,notes:session.notes||null};
        const updated=await api(`/api/academy/sessions/${sessionId}`,{method:'PUT',body:JSON.stringify(payload)});
        const channels=channelsFromForm(form);
        const eventRecord=await queueSessionNotification(updated,'session_rescheduled',channels,`Session rescheduled to ${updated.session_date} ${updated.start_time}.`,{before,after:{session_date:updated.session_date,start_time:updated.start_time}});
        closeDialog();notify(eventRecord?`Session rescheduled. Notification event recorded for ${eventRecord.recipient_count} recipient(s).`:'Session rescheduled.');refreshDashboard();
      }catch(error){$('#academyOwnerActionStatus',form).textContent=error.message;button.disabled=false;}
    };
  }
  async function cancelSession(sessionId){
    let session;try{session=await api(`/api/academy/sessions/${sessionId}`);}catch(error){notify(error.message);return;}
    const dialog=openDialog(`<form method="dialog" id="academyOwnerCancelForm"><div class="academy-owner-dialog-head"><div><span>SESSION ACTION</span><h2>Cancel Session</h2><p>${esc(session.batch_name||'1-to-1 Session')} · ${esc(session.session_date)} ${esc(session.start_time)}</p></div><button type="button" data-owner-dialog-close>×</button></div><label class="academy-field"><span>Reason</span><textarea name="reason" rows="3" placeholder="Weather, facility closure, coach unavailable…"></textarea></label>${notificationOptions()}<div class="academy-form-actions"><span id="academyOwnerActionStatus"></span><button type="submit" class="danger">Confirm Cancellation</button></div></form>`);
    const form=$('#academyOwnerCancelForm',dialog);
    form.onsubmit=async event=>{
      event.preventDefault();const button=form.querySelector('button[type="submit"]');button.disabled=true;
      try{
        const fd=new FormData(form);const reason=String(fd.get('reason')||'').trim();
        const cancelled=await api(`/api/academy/sessions/${sessionId}/cancel`,{method:'POST',body:JSON.stringify({reason:reason||null})});
        const channels=channelsFromForm(form);
        const eventRecord=await queueSessionNotification(cancelled,'session_cancelled',channels,`Session on ${cancelled.session_date} at ${cancelled.start_time} was cancelled${reason?`: ${reason}`:'.'}`,{reason});
        closeDialog();notify(eventRecord?`Session cancelled. Notification event recorded for ${eventRecord.recipient_count} recipient(s).`:'Session cancelled.');refreshDashboard();
      }catch(error){$('#academyOwnerActionStatus',form).textContent=error.message;button.disabled=false;}
    };
  }
  async function enhanceDashboardActions(){
    const info=route();if(info.tab!=='overview')return;
    const content=$('#academyWorkspace .academy-content');if(!content||!$('.academy-dash-session',content))return;
    if($('.academy-owner-session-actions',content))return;
    let data;try{data=await dashboardData();}catch{return;}
    const sessions=[...(data.today_sessions?.group||[]),...(data.today_sessions?.private||[])];
    const rows=$$('.academy-dash-session',content);
    rows.forEach((row,index)=>{
      const session=sessions[index];if(!session)return;
      const actions=document.createElement('div');actions.className='academy-owner-session-actions';
      actions.innerHTML=`<button type="button" data-owner-reschedule="${session.id}">Reschedule</button><button type="button" class="danger" data-owner-cancel="${session.id}">Cancel</button>`;
      row.appendChild(actions);
    });
    $$('[data-owner-reschedule]',content).forEach(button=>button.onclick=()=>rescheduleSession(Number(button.dataset.ownerReschedule)));
    $$('[data-owner-cancel]',content).forEach(button=>button.onclick=()=>cancelSession(Number(button.dataset.ownerCancel)));
  }

  async function apply(){
    if(applying){rerunRequested=true;return;}
    applying=true;
    try{
      const info=route();if(info.page!=='academy')return;
      const me=await authMe();
      if(!isOwner(me)){resetOwnerTabs();return;}
      normalizeOwnerTabs();
      renderSettings();
      await renderPlayer360();
      addProgramsContext();
      await enhancePlayerDirectory();
      await enhanceDashboardSnapshot();
      await enhanceDashboardActions();
    }finally{
      applying=false;
      if(rerunRequested){rerunRequested=false;schedule();}
    }
  }
  function schedule(){
    if(applying){rerunRequested=true;return;}
    if(scheduled)return;
    scheduled=true;
    setTimeout(()=>{scheduled=false;apply();},30);
  }
  window.addEventListener('hashchange',()=>{meLoaded=false;cachedMe=null;dashboardCache=null;schedule();});
  document.addEventListener('DOMContentLoaded',schedule);
  new MutationObserver(()=>{if(route().page==='academy')schedule();}).observe(document.documentElement,{childList:true,subtree:true});
  schedule();
})();