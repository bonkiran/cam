(() => {
  const qs=(s,r=document)=>r.querySelector(s);
  const qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  const TABS=[
    ['overview','Overview'],['setup','Academy Setup'],['players','Players'],['batches','Batches & Sessions'],
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
    location.hash=tab==='overview'?'academy':`academy?tab=${encodeURIComponent(tab)}`;
  }
  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function notify(message){
    if(typeof window.toast==='function') window.toast(message); else console.log(message);
  }
  async function requestJson(url,options={}){
    const res=await fetch(url,{cache:'no-store',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    let data=null; try{data=await res.json();}catch{}
    if(!res.ok) throw new Error(data?.detail||`Request failed (${res.status})`);
    return data;
  }
  async function getJson(url){return requestJson(url,{headers:{}});}

  function tabs(active){
    return `<div class="academy-tabs">${TABS.map(([id,label])=>`<button class="${id===active?'active':''}" data-academy-tab="${id}">${label}</button>`).join('')}</div>`;
  }
  function metric(label,value,note,kind='green'){
    const icon=kind==='green'?'♙':kind==='blue'?'▦':kind==='amber'?'◷':'◎';
    return `<article class="academy-stat ${kind}"><div class="academy-stat-icon">${icon}</div><div><span>${label}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></div></article>`;
  }
  function moduleCard(icon,title,text,tab,meta='Foundation'){
    return `<button class="academy-module" data-academy-tab="${tab}"><span class="academy-module-icon">${icon}</span><span class="academy-module-copy"><strong>${title}</strong><small>${text}</small></span><span class="academy-module-meta">${meta}</span><b>→</b></button>`;
  }
  function foundation(title,description,fields){
    return `<section class="academy-two-col"><article class="panel academy-foundation-card"><div class="academy-kicker">NEXT BUILD SLICE</div><h2>${title}</h2><p>${description}</p><div class="academy-field-list">${fields.map(x=>`<span>${x}</span>`).join('')}</div><div class="academy-foundation-note"><strong>Not active yet.</strong> We will implement and test this module only after Slice 1 — Academy Setup, Players and Guardians — is verified end-to-end.</div></article><article class="panel academy-link-card"><div class="academy-kicker">CONNECTED PLAYER DEVELOPMENT</div><h2>Use the same player record</h2><p>Academy operations attach to the existing CrickAnalysis player, video, event and biomechanics history instead of creating another player identity.</p><div class="academy-journey"><span>Enrollment</span><i>→</i><span>Session</span><i>→</i><span>Coach feedback</span><i>→</i><span>Video evidence</span><i>→</i><span>Progress</span></div></article></section>`;
  }

  function academySetup(profile){
    const p=profile||{};
    return `<section class="academy-section-head"><div><span class="academy-kicker">SLICE 1 · ACADEMY MASTER PROFILE</span><h1>Academy Setup</h1><p>This profile becomes the organization record used by players, schedules, billing, payments and communications.</p></div></section>
    <form id="academyProfileForm" class="panel academy-form-card">
      <div class="academy-form-section"><div><h2>Academy Information</h2><p>Core organization and contact information.</p></div><div class="academy-form-grid two">
        ${field('Academy Name','name',p.name,'text',true)}${field('Email','email',p.email,'email')}${field('Phone','phone',p.phone)}${field('Website','website',p.website,'url')}
      </div></div>
      <div class="academy-form-section"><div><h2>Primary Location</h2><p>We will support multiple locations later; Slice 1 establishes the primary academy address.</p></div><div class="academy-form-grid two">
        ${field('Address Line 1','address_line1',p.address_line1)}${field('Address Line 2','address_line2',p.address_line2)}${field('City','city',p.city)}${field('State / Province','state',p.state)}${field('ZIP / Postal Code','postal_code',p.postal_code)}${field('Country','country',p.country||'United States')}${field('Timezone','timezone',p.timezone||'America/New_York')}
      </div></div>
      <div class="academy-form-actions"><span id="academySaveStatus"></span><button type="submit" class="primary">Save Academy Profile</button></div>
    </form>`;
  }

  function field(label,name,value='',type='text',required=false,placeholder=''){
    return `<label class="academy-field"><span>${label}${required?' *':''}</span><input type="${type}" name="${name}" value="${esc(value||'')}" ${required?'required':''} placeholder="${esc(placeholder)}"></label>`;
  }
  function selectField(label,name,value,options){
    return `<label class="academy-field"><span>${label}</span><select name="${name}"><option value="">Select</option>${options.map(o=>`<option value="${esc(o)}" ${String(value||'')===o?'selected':''}>${esc(o)}</option>`).join('')}</select></label>`;
  }
  function textArea(label,name,value=''){
    return `<label class="academy-field academy-field-wide"><span>${label}</span><textarea name="${name}" rows="3">${esc(value||'')}</textarea></label>`;
  }

  function guardianForm(g={},index=0){
    return `<div class="guardian-card" data-guardian-card data-guardian-id="${esc(g.id||'')}">
      <div class="guardian-card-head"><div><strong>Guardian ${index+1}</strong><small>Parent/guardian, billing and pickup contact.</small></div><button type="button" class="danger guardian-remove">Remove</button></div>
      <div class="academy-form-grid two">
        ${field('First Name','guardian_first_name',g.first_name,'text',true)}${field('Last Name','guardian_last_name',g.last_name,'text',true)}
        ${field('Relationship','guardian_relationship',g.relationship,'text',false,'Mother, Father, Guardian…')}${field('Phone','guardian_phone',g.phone)}${field('Email','guardian_email',g.email,'email')}
      </div>
      <div class="guardian-flags">
        <label><input type="checkbox" name="guardian_is_primary" ${g.is_primary?'checked':''}> Primary guardian</label>
        <label><input type="checkbox" name="guardian_billing_contact" ${g.billing_contact?'checked':''}> Billing contact</label>
        <label><input type="checkbox" name="guardian_pickup_authorized" ${g.pickup_authorized===0||g.pickup_authorized===false?'':'checked'}> Authorized pickup</label>
      </div>
    </div>`;
  }

  function playerForm(player=null){
    const p=player||{};
    const guardians=(p.guardians||[]);
    return `<form id="academyPlayerForm" class="panel academy-form-card" data-player-id="${esc(p.id||'')}">
      <div class="academy-form-title"><div><span class="academy-kicker">${p.id?'EDIT PLAYER':'NEW PLAYER'}</span><h2>${p.id?'Update Player':'Add Player'}</h2><p>This is the same player record used by CrickAnalysis video and development history.</p></div><button type="button" class="secondary" id="cancelPlayerForm">Cancel</button></div>
      <div class="academy-form-section"><div><h2>Player Information</h2><p>Identity and academy status.</p></div><div class="academy-form-grid three">
        ${field('Full Display Name','name',p.name,'text',true)}${field('First Name','first_name',p.first_name)}${field('Last Name','last_name',p.last_name)}${field('Preferred Name','preferred_name',p.preferred_name)}${field('Date of Birth','date_of_birth',p.date_of_birth,'date')}${selectField('Gender','gender',p.gender,['Female','Male','Non-binary','Prefer not to say'])}${field('Joined On','joined_on',p.joined_on,'date')}${selectField('Status','status',p.status||'active',['active','inactive','waitlisted'])}
      </div></div>
      <div class="academy-form-section"><div><h2>Cricket Profile</h2><p>Initial cricket characteristics; deeper assessments come later.</p></div><div class="academy-form-grid three">
        ${selectField('Batting Style','batting_style',p.batting_style,['Right-handed','Left-handed'])}${field('Bowling Style','bowling_style',p.bowling_style,'text',false,'Right-arm fast, leg spin…')}${selectField('Handedness','handedness',p.handedness,['Right','Left'])}${selectField('Skill Level','skill_level',p.skill_level,['Beginner','Developing','Intermediate','Advanced','Elite'])}
      </div></div>
      <div class="academy-form-section"><div><h2>Player Contact & Address</h2><p>Use player contact where appropriate; guardian details are maintained separately.</p></div><div class="academy-form-grid three">
        ${field('Email','email',p.email,'email')}${field('Phone','phone',p.phone)}${field('Address Line 1','address_line1',p.address_line1)}${field('Address Line 2','address_line2',p.address_line2)}${field('City','city',p.city)}${field('State','state',p.state)}${field('ZIP / Postal Code','postal_code',p.postal_code)}${field('Country','country',p.country)}
      </div></div>
      <div class="academy-form-section"><div><h2>Emergency Contact</h2><p>Quick-access emergency information for academy staff.</p></div><div class="academy-form-grid two">${field('Emergency Contact Name','emergency_contact_name',p.emergency_contact_name)}${field('Emergency Contact Phone','emergency_contact_phone',p.emergency_contact_phone)}</div></div>
      <div class="academy-form-section"><div class="academy-section-row"><div><h2>Parents / Guardians</h2><p>Add one or more guardian contacts. Billing flags will be used by the future payments module.</p></div><button type="button" class="secondary" id="addGuardian">＋ Add Guardian</button></div><div id="guardianList" class="guardian-list">${guardians.map((g,i)=>guardianForm(g,i)).join('')}</div></div>
      <div class="academy-form-section"><div><h2>Internal Notes</h2></div><div class="academy-form-grid">${textArea('Notes','notes',p.notes)}</div></div>
      <div class="academy-form-actions"><span id="playerSaveStatus"></span><button type="submit" class="primary">${p.id?'Save Changes':'Create Player'}</button></div>
    </form>`;
  }

  function playerRows(players){
    if(!players.length) return `<div class="academy-empty"><strong>No academy players yet</strong><span>Choose Add Player to create the first complete academy player record.</span></div>`;
    return players.map(p=>{
      const initials=String(p.name||'?').split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase();
      const primary=(p.guardians||[]).find(g=>Number(g.is_primary)===1)||(p.guardians||[])[0];
      const secondary=[p.skill_level,p.batting_style].filter(Boolean).join(' · ')||'Cricket profile not completed';
      return `<div class="academy-player-row detailed" data-player-id="${p.id}"><div class="academy-avatar">${esc(initials)}</div><div><strong>${esc(p.name)}</strong><small>${esc(secondary)}</small><small>${primary?`Guardian: ${esc(primary.first_name)} ${esc(primary.last_name)}${primary.phone?` · ${esc(primary.phone)}`:''}`:'Guardian not added'}</small></div><span class="academy-status ${esc(p.status||'active')}">${esc(p.status||'active')}</span><div class="academy-row-actions"><button data-edit-player="${p.id}">Edit</button><button data-go-route="analyses">Development →</button></div></div>`;
    }).join('');
  }

  function playersPage(players){
    return `<section class="academy-section-head"><div><span class="academy-kicker">SLICE 1 · UNIFIED PLAYER DIRECTORY</span><h1>Academy Players</h1><p>Create and maintain player, cricket profile, emergency and guardian information on the same record used by video analysis.</p></div><button class="primary" id="addAcademyPlayer">＋ Add Player</button></section>
      <div id="playerEditor"></div>
      <article class="panel academy-player-panel"><div class="panel-head"><div><h2>Player Records</h2><p>${players.length} total player${players.length===1?'':'s'} in the current data store.</p></div></div><div class="academy-player-list">${playerRows(players)}</div></article>`;
  }

  function overview(data){
    const players=data.players||[];
    const d=data.dashboard||{};
    const profile=data.academy?.profile;
    const withAnalysis=players.filter(p=>Number(p.completed_analyses||0)>0).length;
    const withGuardian=players.filter(p=>(p.guardians||[]).length>0).length;
    return `<section class="academy-hero"><div><span class="academy-kicker">ACADEMY + PERFORMANCE INTELLIGENCE</span><h1>${profile?esc(profile.name):'Academy Dashboard'}</h1><p>${profile?'Academy operations and player development from one longitudinal record.':'Start by completing Academy Setup, then create the first complete player and guardian record.'}</p></div><div class="academy-hero-actions"><button class="secondary" data-academy-tab="setup">${profile?'Edit Academy Setup':'Complete Academy Setup'}</button><button class="primary" data-academy-tab="players">Manage Players</button></div></section>
    <section class="academy-stats">${metric('Players',players.length,'Unified player profiles','green')}${metric('Guardian contacts',withGuardian,'Players with at least one guardian','blue')}${metric('Players with analysis',withAnalysis,'Have completed video evidence','amber')}${metric('Completed analyses',Number(d.completed_count||0),'Existing development history','gray')}</section>
    <section class="academy-dashboard-grid"><article class="panel academy-operations"><div class="panel-head"><div><h2>Academy Operations</h2><p>We are activating these modules one tested slice at a time.</p></div><span class="academy-badge">SLICE 1 ACTIVE</span></div><div class="academy-module-grid">
    ${moduleCard('⚙','Academy Setup','Organization profile, contact, location and timezone.','setup',profile?'Configured':'Action needed')}
    ${moduleCard('♙','Players & Guardians','Player identity, cricket profile, contacts and guardians.','players',`${players.length} live`)}
    ${moduleCard('▦','Batches & Sessions','Training groups, schedules, capacity and session plans.','batches','Next slice')}
    ${moduleCard('◇','Coaches','Coach profiles, assignments, workload and specialties.','coaches','Next slice')}
    ${moduleCard('✓','Attendance','Player and coach attendance linked to each session.','attendance')}
    ${moduleCard('⚔','Teams & Matches','Squads, fixtures, selection and match linkage.','teams')}
    ${moduleCard('♜','Tournaments','Competition calendar, entries and academy squads.','tournaments')}
    ${moduleCard('$','Fees & Payments','Plans, invoices, payments, balances and reminders.','fees')}
    </div></article><aside class="academy-side-stack"><article class="panel academy-principle"><span class="academy-kicker">SLICE 1 TEST GATE</span><h2>Setup → Player → Guardian</h2><p>Before moving to Programs/Batches, verify that academy information and player/guardian records can be created, reopened and edited correctly.</p><div class="academy-flow"><span>Academy Setup</span><b>→</b><span>Add Player</span><b>→</b><span>Add Guardian</span><b>→</b><span>Edit & Verify</span></div></article><article class="panel academy-today"><div class="panel-head"><div><h2>Data readiness</h2><p>Current Slice 1 completion signals.</p></div></div><div class="academy-readiness"><div><span>Academy profile</span><strong>${profile?'Ready':'Not configured'}</strong></div><div><span>Players</span><strong>${players.length}</strong></div><div><span>Players with guardian</span><strong>${withGuardian}</strong></div></div></article></aside></section>`;
  }

  function content(tab,data){
    if(tab==='overview') return overview(data);
    if(tab==='setup') return academySetup(data.academy?.profile);
    if(tab==='players') return playersPage(data.players||[]);
    if(tab==='batches') return foundation('Batches & Sessions','Create recurring training batches, assign players/coaches, manage capacity and attach a session plan to each practice.',['Batch name','Age / skill level','Days & time','Coach assignment','Capacity','Session plan','Ground / lane']);
    if(tab==='coaches') return foundation('Coaches','Manage coaching staff and connect assignments to the players and sessions they actually work with.',['Coach profile','Specialties','Availability','Batch assignments','Player assignments','Workload','Coach notes']);
    if(tab==='attendance') return foundation('Attendance','Capture attendance at session level so consistency can later be compared with development outcomes.',['Session roster','Present / absent / late','Coach attendance','Reason / note','Attendance %','Player trend','Batch trend']);
    if(tab==='teams') return foundation('Teams & Matches','Build academy squads, fixtures and selections while linking match footage and analysis back to each player.',['Team / age group','Squad','Fixture','Opponent','Venue','Selection','Score / result','Match video']);
    if(tab==='tournaments') return foundation('Tournaments','Track competitions, academy entries, squads, fixtures and development evidence from tournament play.',['Tournament','Dates','Teams entered','Squads','Fixtures','Results','Fees / logistics']);
    if(tab==='fees') return foundation('Fees & Payments','Create fee plans, invoices, payments, balances, receipts and payment reminders.',['Fee plan','Billing cycle','Invoice','Paid / due','Partial payment','Receipt','Outstanding balance','Automated reminder']);
    return overview(data);
  }

  function formDataObject(form){
    const fd=new FormData(form); const obj={};
    for(const [k,v] of fd.entries()) obj[k]=typeof v==='string'?v.trim():v;
    return obj;
  }
  function collectGuardians(){
    return qsa('[data-guardian-card]').map(card=>({
      id:Number(card.dataset.guardianId)||null,
      first_name:qs('[name="guardian_first_name"]',card)?.value.trim()||'',
      last_name:qs('[name="guardian_last_name"]',card)?.value.trim()||'',
      relationship:qs('[name="guardian_relationship"]',card)?.value.trim()||null,
      email:qs('[name="guardian_email"]',card)?.value.trim()||null,
      phone:qs('[name="guardian_phone"]',card)?.value.trim()||null,
      is_primary:!!qs('[name="guardian_is_primary"]',card)?.checked,
      billing_contact:!!qs('[name="guardian_billing_contact"]',card)?.checked,
      pickup_authorized:!!qs('[name="guardian_pickup_authorized"]',card)?.checked,
    })).filter(g=>g.first_name||g.last_name);
  }

  function wireGuardianCards(){
    qsa('.guardian-remove').forEach(btn=>btn.onclick=()=>{
      const card=btn.closest('[data-guardian-card]'); if(card) card.remove();
      qsa('[data-guardian-card]').forEach((c,i)=>{const s=qs('.guardian-card-head strong',c);if(s)s.textContent=`Guardian ${i+1}`;});
    });
  }

  async function openPlayerEditor(id=null){
    const target=qs('#playerEditor'); if(!target)return;
    target.innerHTML='<div class="panel academy-loading">Loading player…</div>';
    try{
      const player=id?await getJson(`/api/academy/players/${id}`):null;
      target.innerHTML=playerForm(player);
      target.scrollIntoView({behavior:'smooth',block:'start'});
      qs('#cancelPlayerForm').onclick=()=>{target.innerHTML='';};
      qs('#addGuardian').onclick=()=>{
        const list=qs('#guardianList'); const count=qsa('[data-guardian-card]',list).length;
        list.insertAdjacentHTML('beforeend',guardianForm({},count)); wireGuardianCards();
      };
      wireGuardianCards();
      qs('#academyPlayerForm').onsubmit=savePlayer;
    }catch(err){target.innerHTML=`<div class="warning">${esc(err.message)}</div>`;}
  }

  async function savePlayer(event){
    event.preventDefault();
    const form=event.currentTarget; const base=formDataObject(form);
    const id=Number(form.dataset.playerId)||null;
    const payload={
      name:base.name,first_name:base.first_name||null,last_name:base.last_name||null,preferred_name:base.preferred_name||null,
      date_of_birth:base.date_of_birth||null,gender:base.gender||null,batting_style:base.batting_style||null,bowling_style:base.bowling_style||null,
      handedness:base.handedness||null,skill_level:base.skill_level||null,email:base.email||null,phone:base.phone||null,
      address_line1:base.address_line1||null,address_line2:base.address_line2||null,city:base.city||null,state:base.state||null,
      postal_code:base.postal_code||null,country:base.country||null,emergency_contact_name:base.emergency_contact_name||null,
      emergency_contact_phone:base.emergency_contact_phone||null,joined_on:base.joined_on||null,status:base.status||'active',notes:base.notes||null,
      guardians:collectGuardians()
    };
    const status=qs('#playerSaveStatus'); const submit=qs('button[type="submit"]',form);
    submit.disabled=true; if(status)status.textContent='Saving…';
    try{
      await requestJson(id?`/api/academy/players/${id}`:'/api/academy/players',{method:id?'PUT':'POST',body:JSON.stringify(payload)});
      notify(id?'Player updated.':'Player created.');
      await render();
    }catch(err){if(status)status.textContent=err.message;submit.disabled=false;}
  }

  function wirePage(tab){
    qsa('[data-academy-tab]').forEach(b=>b.onclick=()=>go(b.dataset.academyTab));
    qsa('[data-go-route]').forEach(b=>b.onclick=()=>{location.hash=b.dataset.goRoute;});
    if(tab==='setup'){
      const form=qs('#academyProfileForm');
      if(form) form.onsubmit=async e=>{
        e.preventDefault(); const payload=formDataObject(form); const status=qs('#academySaveStatus'); const submit=qs('button[type="submit"]',form);
        submit.disabled=true;if(status)status.textContent='Saving…';
        try{await requestJson('/api/academy/profile',{method:'PUT',body:JSON.stringify(payload)});notify('Academy profile saved.');await render();}
        catch(err){if(status)status.textContent=err.message;submit.disabled=false;}
      };
    }
    if(tab==='players'){
      const add=qs('#addAcademyPlayer'); if(add)add.onclick=()=>openPlayerEditor();
      qsa('[data-edit-player]').forEach(b=>b.onclick=()=>openPlayerEditor(Number(b.dataset.editPlayer)));
    }
  }

  async function render(){
    const current=route();
    if(current.page!=='academy') return;
    const token=++renderToken;
    let data={dashboard:{},players:[],academy:{configured:false,profile:null}};
    try{
      const [dashboard,players,academy]=await Promise.all([getJson('/api/dashboard'),getJson('/api/academy/players'),getJson('/api/academy/profile')]);
      data={dashboard,players:Array.isArray(players)?players:[],academy};
    }catch(err){console.warn('Academy data unavailable',err);}
    if(token!==renderToken||route().page!=='academy')return;
    const main=qs('.main');if(!main)return;
    const topbar=qs('.topbar',main);
    qsa(':scope > *',main).forEach(child=>{if(child!==topbar)child.remove();});
    const wrap=document.createElement('div');wrap.id='academyWorkspace';
    wrap.innerHTML=`${tabs(current.tab)}<div class="academy-content">${content(current.tab,data)}</div>`;
    main.appendChild(wrap);
    wirePage(current.tab);
  }

  window.addEventListener('hashchange',()=>setTimeout(render,0));
  document.addEventListener('DOMContentLoaded',render);
  render();
})();
