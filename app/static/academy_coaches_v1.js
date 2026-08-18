(() => {
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  let rendering=false;
  let scheduled=false;

  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function tabFromHash(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    if(page!=='academy')return null;
    return new URLSearchParams(query).get('tab')||'overview';
  }
  async function requestJson(url,options={}){
    const res=await fetch(url,{cache:'no-store',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    let data=null;try{data=await res.json();}catch{}
    if(!res.ok)throw new Error(data?.detail||`Request failed (${res.status})`);
    return data;
  }
  function notify(message){if(typeof window.toast==='function')window.toast(message);else console.log(message);}
  function field(label,name,value='',type='text',required=false,placeholder=''){
    return `<label class="academy-field"><span>${label}${required?' *':''}</span><input type="${type}" name="${name}" value="${esc(value||'')}" ${required?'required':''} placeholder="${esc(placeholder)}"></label>`;
  }
  function select(label,name,value,options,required=false){
    return `<label class="academy-field"><span>${label}${required?' *':''}</span><select name="${name}" ${required?'required':''}>${options.map(o=>{const val=typeof o==='string'?o:o.value;const text=typeof o==='string'?o:o.label;return `<option value="${esc(val)}" ${String(value||'')===String(val)?'selected':''}>${esc(text)}</option>`;}).join('')}</select></label>`;
  }
  function textarea(label,name,value='',placeholder=''){
    return `<label class="academy-field academy-field-wide"><span>${label}</span><textarea name="${name}" rows="3" placeholder="${esc(placeholder)}">${esc(value||'')}</textarea></label>`;
  }
  function formObject(form){const out={};new FormData(form).forEach((v,k)=>out[k]=typeof v==='string'?v.trim():v);return out;}

  function coachForm(c={}){
    const editing=!!c.id;
    return `<form id="academyCoachForm" class="panel academy-form-card" data-coach-id="${esc(c.id||'')}">
      <div class="academy-form-title"><div><span class="academy-kicker">SLICE 2B · ${editing?'EDIT COACH':'NEW COACH'}</span><h2>${editing?'Update Coach':'Add Coach'}</h2><p>Coach identity, contact details, specialties and availability. Session workload will connect in the Batches & Sessions slice.</p></div><button type="button" class="secondary" id="cancelCoachForm">Cancel</button></div>
      <div class="academy-form-section"><div><h2>Coach Profile</h2><p>Identity and academy lifecycle.</p></div><div class="academy-form-grid three">
        ${field('First Name','first_name',c.first_name,'text',true)}${field('Last Name','last_name',c.last_name,'text',true)}${field('Preferred Name','preferred_name',c.preferred_name)}
        ${field('Email','email',c.email,'email')}${field('Phone','phone',c.phone)}${field('Joined On','joined_on',c.joined_on,'date')}${select('Status','status',c.status||'active',['active','inactive'],true)}
      </div></div>
      <div class="academy-form-section"><div><h2>Cricket Expertise</h2><p>Use comma-separated specialties so assignments can later be matched to training needs.</p></div><div class="academy-form-grid two">
        ${field('Specialties','specialties',(c.specialties||[]).join(', '),'text',false,'Batting, Spin Bowling, Wicketkeeping')}${textarea('Certifications','certifications',c.certifications,'ECB/USA Cricket/first aid or other qualifications')}
      </div></div>
      <div class="academy-form-section"><div><h2>Availability</h2><p>Operational availability until calendar-based availability is introduced with Sessions.</p></div><div class="academy-form-grid">${textarea('Availability','availability',c.availability,'Mon/Wed 5–9 PM; Sat mornings')}${textarea('Internal Notes','notes',c.notes)}</div></div>
      <div class="academy-form-actions"><span id="coachSaveStatus"></span><button type="submit" class="primary">${editing?'Save Coach':'Create Coach'}</button></div>
    </form>`;
  }

  function assignmentForm(coaches,players){
    return `<form id="academyCoachAssignmentForm" class="panel academy-form-card">
      <div class="academy-form-title"><div><span class="academy-kicker">SLICE 2B · PLAYER ASSIGNMENT</span><h2>Assign Coach to Player</h2><p>This creates a traceable relationship without changing the player's program or batch enrollment.</p></div><button type="button" class="secondary" id="cancelCoachAssignment">Cancel</button></div>
      <div class="academy-form-section"><div><h2>Assignment</h2></div><div class="academy-form-grid three">
        ${select('Coach','coach_id','',coaches.map(c=>({value:c.id,label:`${c.first_name} ${c.last_name}`})),true)}
        ${select('Player','player_id','',players.map(p=>({value:p.id,label:p.name})),true)}
        ${select('Role','assignment_role','primary',[{value:'primary',label:'Primary'},{value:'support',label:'Support'}],true)}
        ${field('Start Date','start_date','','date')}${textarea('Notes','notes','')}
      </div></div>
      <div class="academy-form-actions"><span id="coachAssignmentStatus"></span><button type="submit" class="primary">Create Assignment</button></div>
    </form>`;
  }

  function endForm(a){
    return `<form id="academyEndCoachAssignmentForm" class="panel academy-form-card" data-assignment-id="${a.id}">
      <div class="academy-form-title"><div><span class="academy-kicker">ASSIGNMENT LIFECYCLE</span><h2>End Coach Assignment</h2><p>${esc(a.coach_name)} → ${esc(a.player_name)}</p></div><button type="button" class="secondary" id="cancelEndCoachAssignment">Cancel</button></div>
      <div class="academy-form-grid two">${field('End Date','end_date',new Date().toISOString().slice(0,10),'date')}</div>
      <div class="academy-form-actions"><span id="endCoachAssignmentStatus"></span><button type="submit" class="primary">End Assignment</button></div>
    </form>`;
  }

  function coachRows(coaches){
    if(!coaches.length)return `<div class="academy-program-empty"><strong>No coaches yet</strong>Add the first coach profile to begin operational assignments.</div>`;
    return coaches.map(c=>{
      const name=`${c.first_name||''} ${c.last_name||''}`.trim();
      const specialties=(c.specialties||[]);
      return `<div class="academy-coach-row" data-coach-row="${c.id}"><div class="academy-avatar">${esc((c.first_name?.[0]||'')+(c.last_name?.[0]||''))}</div><div class="academy-coach-copy"><strong>${esc(name)}</strong><small>${esc(c.email||c.phone||'Contact not added')}</small><div class="academy-program-tags">${specialties.length?specialties.map(s=>`<span>${esc(s)}</span>`).join(''):'<span>No specialties</span>'}<span>${Number(c.assigned_player_count||0)} player assignment${Number(c.assigned_player_count||0)===1?'':'s'}</span></div>${c.availability?`<small>Availability: ${esc(c.availability)}</small>`:''}</div><div class="academy-program-actions"><span class="academy-program-status ${esc(c.status)}">${esc(c.status)}</span><button data-edit-coach="${c.id}">Edit</button></div></div>`;
    }).join('');
  }

  function assignmentRows(assignments){
    if(!assignments.length)return `<div class="academy-program-empty"><strong>No coach-player assignments yet</strong>Assignments will appear here and remain in history after they end.</div>`;
    return assignments.map(a=>`<div class="academy-coach-assignment-row" data-coach-assignment-row="${a.id}"><div><strong>${esc(a.coach_name)} → ${esc(a.player_name)}</strong><small>${esc(a.assignment_role)}${a.start_date?` · Start: ${esc(a.start_date)}`:''}${a.end_date?` · End: ${esc(a.end_date)}`:''}</small>${a.notes?`<small>${esc(a.notes)}</small>`:''}</div><div class="academy-program-actions"><span class="academy-program-status ${esc(a.status)}">${esc(a.status)}</span>${a.status==='active'?`<button class="danger" data-end-coach-assignment="${a.id}">End</button>`:''}</div></div>`).join('');
  }

  function pageHtml(coaches,assignments,players){
    const active=coaches.filter(c=>c.status==='active');
    const withSpecialties=coaches.filter(c=>(c.specialties||[]).length).length;
    const activeAssignments=assignments.filter(a=>a.status==='active').length;
    return `<section class="academy-section-head"><div><span class="academy-kicker">SLICE 2B · COACH OPERATIONS</span><h1>Coaches</h1><p>Maintain coach profiles and connect coaches directly to players. Batches and session workload attach to these same coach records next.</p></div><div class="academy-hero-actions"><button class="secondary" id="openCoachAssignment">＋ Assign Player</button><button class="primary" id="openCoachForm">＋ Add Coach</button></div></section>
      <section class="academy-stats"><article class="academy-stat green"><div class="academy-stat-icon">◇</div><div><span>Active coaches</span><strong>${active.length}</strong><small>${coaches.length} total profiles</small></div></article><article class="academy-stat blue"><div class="academy-stat-icon">♙</div><div><span>Player assignments</span><strong>${activeAssignments}</strong><small>Current direct assignments</small></div></article><article class="academy-stat amber"><div class="academy-stat-icon">◎</div><div><span>Specialty profiles</span><strong>${withSpecialties}</strong><small>Coaches with expertise recorded</small></div></article><article class="academy-stat gray"><div class="academy-stat-icon">▦</div><div><span>Session workload</span><strong>—</strong><small>Activates with Sessions</small></div></article></section>
      <div id="coachEditor" class="academy-program-editor"></div><div id="coachAssignmentEditor" class="academy-program-editor"></div>
      <section class="academy-programs-grid"><article class="panel academy-programs-panel"><div class="panel-head"><div><h2>Coach Directory</h2><p>${coaches.length} coach profile${coaches.length===1?'':'s'}.</p></div></div><div class="academy-coach-list">${coachRows(coaches)}</div></article>
      <article class="panel academy-programs-panel"><div class="panel-head"><div><h2>Player Assignment History</h2><p>${assignments.length} assignment record${assignments.length===1?'':'s'} retained.</p></div></div><div class="academy-coach-assignment-list">${assignmentRows(assignments)}</div></article></section>`;
  }

  async function renderCoaches(force=false){
    if(rendering||tabFromHash()!=='coaches')return;
    const content=$('#academyWorkspace .academy-content');
    if(!content)return;
    if(!force&&content.dataset.coachesRendered==='1')return;
    rendering=true;content.dataset.coachesRendered='loading';content.innerHTML='<div class="panel academy-loading">Loading coach operations…</div>';
    try{
      const [coaches,assignments,players]=await Promise.all([
        requestJson('/api/academy/coaches'),requestJson('/api/academy/coach-player-assignments'),requestJson('/api/academy/players')
      ]);
      if(tabFromHash()!=='coaches')return;
      content.innerHTML=pageHtml(coaches,assignments,players);content.dataset.coachesRendered='1';wire(coaches,assignments,players);
    }catch(err){content.innerHTML=`<div class="warning">${esc(err.message)}</div>`;content.dataset.coachesRendered='1';}
    finally{rendering=false;}
  }

  function wire(coaches,assignments,players){
    const coachEditor=$('#coachEditor');const assignmentEditor=$('#coachAssignmentEditor');
    $('#openCoachForm')?.addEventListener('click',()=>{coachEditor.innerHTML=coachForm();wireCoachForm(coachEditor);coachEditor.scrollIntoView({behavior:'smooth',block:'start'});});
    $('#openCoachAssignment')?.addEventListener('click',()=>{
      const eligibleCoaches=coaches.filter(c=>c.status==='active');const eligiblePlayers=players.filter(p=>p.status==='active');
      if(!eligibleCoaches.length||!eligiblePlayers.length){notify('Create an active coach and active player before assigning.');return;}
      assignmentEditor.innerHTML=assignmentForm(eligibleCoaches,eligiblePlayers);wireAssignmentForm(assignmentEditor);assignmentEditor.scrollIntoView({behavior:'smooth',block:'start'});
    });
    $$('[data-edit-coach]').forEach(btn=>btn.onclick=()=>{const c=coaches.find(x=>Number(x.id)===Number(btn.dataset.editCoach));coachEditor.innerHTML=coachForm(c||{});wireCoachForm(coachEditor);coachEditor.scrollIntoView({behavior:'smooth',block:'start'});});
    $$('[data-end-coach-assignment]').forEach(btn=>btn.onclick=()=>{const a=assignments.find(x=>Number(x.id)===Number(btn.dataset.endCoachAssignment));assignmentEditor.innerHTML=endForm(a);wireEndForm(assignmentEditor);assignmentEditor.scrollIntoView({behavior:'smooth',block:'start'});});
  }

  function wireCoachForm(editor){
    $('#cancelCoachForm',editor).onclick=()=>editor.innerHTML='';
    $('#academyCoachForm',editor).onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget;const raw=formObject(form);const id=Number(form.dataset.coachId)||null;const status=$('#coachSaveStatus',form);const submit=$('button[type="submit"]',form);submit.disabled=true;status.textContent='Saving…';
      const payload={...raw,preferred_name:raw.preferred_name||null,email:raw.email||null,phone:raw.phone||null,joined_on:raw.joined_on||null,availability:raw.availability||null,certifications:raw.certifications||null,notes:raw.notes||null,specialties:(raw.specialties||'').split(',').map(x=>x.trim()).filter(Boolean)};
      delete payload.specialties_text;
      try{await requestJson(id?`/api/academy/coaches/${id}`:'/api/academy/coaches',{method:id?'PUT':'POST',body:JSON.stringify(payload)});notify(id?'Coach updated.':'Coach created.');await renderCoaches(true);}catch(err){status.textContent=err.message;submit.disabled=false;}
    };
  }

  function wireAssignmentForm(editor){
    $('#cancelCoachAssignment',editor).onclick=()=>editor.innerHTML='';
    $('#academyCoachAssignmentForm',editor).onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget;const raw=formObject(form);const status=$('#coachAssignmentStatus',form);const submit=$('button[type="submit"]',form);submit.disabled=true;status.textContent='Saving…';
      const payload={coach_id:Number(raw.coach_id),player_id:Number(raw.player_id),assignment_role:raw.assignment_role,start_date:raw.start_date||null,notes:raw.notes||null};
      try{await requestJson('/api/academy/coach-player-assignments',{method:'POST',body:JSON.stringify(payload)});notify('Coach assigned to player.');await renderCoaches(true);}catch(err){status.textContent=err.message;submit.disabled=false;}
    };
  }

  function wireEndForm(editor){
    $('#cancelEndCoachAssignment',editor).onclick=()=>editor.innerHTML='';
    $('#academyEndCoachAssignmentForm',editor).onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget;const id=Number(form.dataset.assignmentId);const date=new FormData(form).get('end_date')||'';const status=$('#endCoachAssignmentStatus',form);status.textContent='Saving…';
      try{await requestJson(`/api/academy/coach-player-assignments/${id}/end?end_date=${encodeURIComponent(date)}`,{method:'POST',body:'{}'});notify('Coach assignment ended.');await renderCoaches(true);}catch(err){status.textContent=err.message;}
    };
  }

  function schedule(){if(scheduled)return;scheduled=true;setTimeout(()=>{scheduled=false;renderCoaches();},35);}
  window.addEventListener('hashchange',schedule);
  new MutationObserver(()=>{if(tabFromHash()==='coaches')schedule();}).observe(document.documentElement,{childList:true,subtree:true});
  schedule();
})();
