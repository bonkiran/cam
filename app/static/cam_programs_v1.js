(() => {
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  let scheduled=false;
  let rendering=false;

  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function tabFromHash(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    if(page!=='cam') return null;
    return new URLSearchParams(query).get('tab')||'overview';
  }
  async function requestJson(url,options={}){
    const res=await fetch(url,{cache:'no-store',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    let data=null;try{data=await res.json();}catch{}
    if(!res.ok) throw new Error(data?.detail||`Request failed (${res.status})`);
    return data;
  }
  function notify(message){
    if(typeof window.toast==='function') window.toast(message); else console.log(message);
  }
  function ensureTab(){
    const tabs=$('.cam-tabs'); if(!tabs)return;
    let btn=$('#camProgramsTab',tabs);
    if(!btn){
      btn=document.createElement('button');
      btn.id='camProgramsTab';
      btn.textContent='Programs & Enrollment';
      btn.onclick=()=>{location.hash='cam?tab=programs';};
      const players=$$('button',tabs).find(b=>b.textContent.trim()==='Players');
      if(players?.nextSibling) tabs.insertBefore(btn,players.nextSibling); else tabs.appendChild(btn);
    }
    btn.classList.toggle('active',tabFromHash()==='programs');
  }
  function field(label,name,value='',type='text',required=false,placeholder=''){
    return `<label class="cam-field"><span>${label}${required?' *':''}</span><input type="${type}" name="${name}" value="${esc(value||'')}" ${required?'required':''} placeholder="${esc(placeholder)}"></label>`;
  }
  function select(label,name,value,options,required=false){
    return `<label class="cam-field"><span>${label}${required?' *':''}</span><select name="${name}" ${required?'required':''}><option value="">Select</option>${options.map(o=>{const val=typeof o==='string'?o:o.value;const text=typeof o==='string'?o:o.label;return `<option value="${esc(val)}" ${String(value||'')===String(val)?'selected':''}>${esc(text)}</option>`;}).join('')}</select></label>`;
  }
  function textarea(label,name,value=''){
    return `<label class="cam-field cam-field-wide"><span>${label}</span><textarea name="${name}" rows="3">${esc(value||'')}</textarea></label>`;
  }
  function programForm(p={}){
    const editing=!!p.id;
    return `<form id="camProgramForm" class="panel cam-form-card" data-program-id="${esc(p.id||'')}">
      <div class="cam-form-title"><div><span class="cam-kicker">SLICE 2A · ${editing?'EDIT PROGRAM':'NEW PROGRAM'}</span><h2>${editing?'Update Program':'Create Program'}</h2><p>Define a reusable academy training program. Billing linkage is intentionally deferred until Fees & Payments.</p></div><button type="button" class="secondary" id="cancelProgramForm">Cancel</button></div>
      <div class="cam-form-section"><div><h2>Program Definition</h2><p>Name, target group and lifecycle.</p></div><div class="cam-form-grid three">
        ${field('Program Name','name',p.name,'text',true)}${field('Code','code',p.code,'text',false,'U15-AB')}${select('Program Type','program_type',p.program_type||'group',[{value:'group',label:'Group'},{value:'private',label:'Private'},{value:'camp',label:'Camp'},{value:'clinic',label:'Clinic'},{value:'other',label:'Other'}],true)}
        ${field('Age Group','age_group',p.age_group,'text',false,'U11, U13, U15…')}${field('Skill Level','skill_level',p.skill_level,'text',false,'Beginner, Advanced…')}${select('Status','status',p.status||'active',['active','inactive'],true)}
        ${field('Start Date','start_date',p.start_date,'date')}${field('End Date','end_date',p.end_date,'date')}
        ${textarea('Description','description',p.description)}
      </div></div>
      <div class="cam-form-actions"><span id="programSaveStatus"></span><button type="submit" class="primary">${editing?'Save Program':'Create Program'}</button></div>
    </form>`;
  }
  function enrollmentForm(players,programs){
    return `<form id="camEnrollmentForm" class="panel cam-form-card">
      <div class="cam-form-title"><div><span class="cam-kicker">SLICE 2A · NEW ENROLLMENT</span><h2>Enroll Player</h2><p>Create a regular or trial enrollment. Only active players and active programs are eligible.</p></div><button type="button" class="secondary" id="cancelEnrollmentForm">Cancel</button></div>
      <div class="cam-form-section"><div><h2>Enrollment</h2><p>Program membership and effective dates.</p></div><div class="cam-form-grid three">
        ${select('Player','player_id','',players.map(p=>({value:p.id,label:p.name})),true)}${select('Program','program_id','',programs.map(p=>({value:p.id,label:p.name})),true)}${select('Enrollment Type','enrollment_type','regular',[{value:'regular',label:'Regular'},{value:'trial',label:'Trial'}],true)}
        ${field('Start Date','start_date','','date')}${field('End Date','end_date','','date')}${textarea('Notes','notes','')}
      </div></div>
      <div class="cam-form-actions"><span id="enrollmentSaveStatus"></span><button type="submit" class="primary">Create Enrollment</button></div>
    </form>`;
  }
  function actionForm(enrollment,action){
    const freeze=action==='freeze';
    return `<form id="camEnrollmentActionForm" class="panel cam-form-card" data-enrollment-id="${enrollment.id}" data-action="${action}">
      <div class="cam-form-title"><div><span class="cam-kicker">ENROLLMENT ACTION</span><h2>${freeze?'Freeze':'Cancel'} Enrollment</h2><p>${esc(enrollment.player_name)} · ${esc(enrollment.program_name)}</p></div><button type="button" class="secondary" id="cancelEnrollmentAction">Cancel</button></div>
      <div class="cam-form-section"><div><h2>${freeze?'Freeze details':'Cancellation details'}</h2><p>This changes lifecycle status without deleting history.</p></div><div class="cam-form-grid two">
        ${field('Effective Date','effective_date',new Date().toISOString().slice(0,10),'date')}${freeze?'':field('Reason','reason','','text',false,'Schedule conflict, moved academy…')}
      </div></div>
      <div class="cam-form-actions"><span id="enrollmentActionStatus"></span><button type="submit" class="primary">Confirm ${freeze?'Freeze':'Cancellation'}</button></div>
    </form>`;
  }
  function programRows(programs){
    if(!programs.length)return `<div class="cam-program-empty"><strong>No programs yet</strong>Create the first academy program before enrolling players.</div>`;
    return programs.map(p=>`<div class="cam-program-row" data-program-row="${p.id}"><div><strong>${esc(p.name)}</strong><small>${esc(p.description||'No description')}</small><div class="cam-program-tags"><span>${esc(p.program_type||'group')}</span>${p.age_group?`<span>${esc(p.age_group)}</span>`:''}${p.skill_level?`<span>${esc(p.skill_level)}</span>`:''}<span>${Number(p.current_enrollment_count||0)} current</span></div></div><div class="cam-program-actions"><span class="cam-program-status ${esc(p.status)}">${esc(p.status)}</span><button data-edit-program="${p.id}">Edit</button></div></div>`).join('');
  }
  function enrollmentRows(enrollments){
    if(!enrollments.length)return `<div class="cam-program-empty"><strong>No enrollment history yet</strong>Enroll an active player into an active program.</div>`;
    return enrollments.map(e=>{
      const canFreeze=e.status==='active';
      const canCancel=e.status!=='cancelled';
      return `<div class="cam-enrollment-row" data-enrollment-row="${e.id}"><div><strong>${esc(e.player_name)} → ${esc(e.program_name)}</strong><div class="cam-enrollment-meta"><span class="cam-enrollment-type">${esc(e.enrollment_type)}</span><span>Start: ${esc(e.start_date||'—')}</span>${e.end_date?`<span>End: ${esc(e.end_date)}</span>`:''}${e.frozen_on?`<span>Frozen: ${esc(e.frozen_on)}</span>`:''}${e.cancelled_on?`<span>Cancelled: ${esc(e.cancelled_on)}</span>`:''}</div>${e.cancellation_reason?`<small>Reason: ${esc(e.cancellation_reason)}</small>`:''}</div><div class="cam-enrollment-actions"><span class="cam-program-status ${esc(e.status)}">${esc(e.status)}</span>${canFreeze?`<button class="warn" data-freeze-enrollment="${e.id}">Freeze</button>`:''}${canCancel?`<button class="danger" data-cancel-enrollment="${e.id}">Cancel</button>`:''}</div></div>`;
    }).join('');
  }
  function pageHtml(programs,enrollments,players){
    const activePrograms=programs.filter(p=>p.status==='active');
    const activePlayers=players.filter(p=>p.status==='active');
    const active=enrollments.filter(e=>e.status==='active').length;
    const trials=enrollments.filter(e=>e.status==='active'&&e.enrollment_type==='trial').length;
    const frozen=enrollments.filter(e=>e.status==='frozen').length;
    return `<section class="cam-section-head"><div><span class="cam-kicker">SLICE 2A · PROGRAMS & ENROLLMENT</span><h1>Programs & Enrollment</h1><p>Define academy offerings and manage each player's enrollment lifecycle without creating a second player identity.</p></div><div class="cam-hero-actions"><button class="secondary" id="openEnrollmentForm">＋ Enroll Player</button><button class="primary" id="openProgramForm">＋ Add Program</button></div></section>
      <section class="cam-stats"><article class="cam-stat green"><div class="cam-stat-icon">▦</div><div><span>Active programs</span><strong>${activePrograms.length}</strong><small>${programs.length} total</small></div></article><article class="cam-stat blue"><div class="cam-stat-icon">♙</div><div><span>Current enrollments</span><strong>${active}</strong><small>Active memberships</small></div></article><article class="cam-stat amber"><div class="cam-stat-icon">◷</div><div><span>Active trials</span><strong>${trials}</strong><small>Trial enrollment type</small></div></article><article class="cam-stat gray"><div class="cam-stat-icon">◎</div><div><span>Frozen</span><strong>${frozen}</strong><small>History retained</small></div></article></section>
      <div id="programEditor" class="cam-program-editor"></div><div id="enrollmentEditor" class="cam-program-editor"></div>
      <section class="cam-programs-grid"><article class="panel cam-programs-panel"><div class="panel-head"><div><h2>Programs</h2><p>${programs.length} program${programs.length===1?'':'s'} defined.</p></div></div><div class="cam-program-list">${programRows(programs)}</div><div class="cam-programs-note"><strong>Billing linkage:</strong> Fee plans and enrollment discounts will connect here when the Fees & Payments slice is built; no financial values are fabricated in this slice.</div></article>
      <article class="panel cam-programs-panel"><div class="panel-head"><div><h2>Enrollment History</h2><p>${enrollments.length} enrollment record${enrollments.length===1?'':'s'} retained across active, frozen and cancelled states.</p></div></div><div class="cam-enrollment-list">${enrollmentRows(enrollments)}</div></article></section>`;
  }
  function formObject(form){
    const out={};new FormData(form).forEach((v,k)=>out[k]=typeof v==='string'?v.trim():v);return out;
  }
  async function renderPrograms(force=false){
    if(rendering)return;
    const content=$('#camWorkspace .cam-content');
    if(!content||tabFromHash()!=='programs')return;
    if(!force&&content.dataset.programsRendered==='1')return;
    rendering=true;
    content.dataset.programsRendered='loading';
    content.innerHTML='<div class="panel cam-loading">Loading programs and enrollment history…</div>';
    try{
      const [programs,enrollments,players]=await Promise.all([
        requestJson('/api/cam/programs'),requestJson('/api/cam/enrollments'),requestJson('/api/cam/players')
      ]);
      if(tabFromHash()!=='programs')return;
      content.innerHTML=pageHtml(programs,enrollments,players);
      content.dataset.programsRendered='1';
      wire(programs,enrollments,players);
    }catch(err){content.innerHTML=`<div class="warning">${esc(err.message)}</div>`;content.dataset.programsRendered='1';}
    finally{rendering=false;}
  }
  function wire(programs,enrollments,players){
    const programEditor=$('#programEditor');const enrollmentEditor=$('#enrollmentEditor');
    $('#openProgramForm')?.addEventListener('click',()=>{
      programEditor.innerHTML=programForm();wireProgramForm(programEditor,programs,enrollments,players);programEditor.scrollIntoView({behavior:'smooth',block:'start'});
    });
    $('#openEnrollmentForm')?.addEventListener('click',()=>{
      const eligiblePlayers=players.filter(p=>p.status==='active');const eligiblePrograms=programs.filter(p=>p.status==='active');
      if(!eligiblePlayers.length||!eligiblePrograms.length){notify('Create an active player and active program before enrolling.');return;}
      enrollmentEditor.innerHTML=enrollmentForm(eligiblePlayers,eligiblePrograms);wireEnrollmentForm(enrollmentEditor);enrollmentEditor.scrollIntoView({behavior:'smooth',block:'start'});
    });
    $$('[data-edit-program]').forEach(btn=>btn.onclick=()=>{
      const p=programs.find(x=>Number(x.id)===Number(btn.dataset.editProgram));programEditor.innerHTML=programForm(p||{});wireProgramForm(programEditor,programs,enrollments,players);programEditor.scrollIntoView({behavior:'smooth',block:'start'});
    });
    $$('[data-freeze-enrollment]').forEach(btn=>btn.onclick=()=>openEnrollmentAction(enrollments,Number(btn.dataset.freezeEnrollment),'freeze'));
    $$('[data-cancel-enrollment]').forEach(btn=>btn.onclick=()=>openEnrollmentAction(enrollments,Number(btn.dataset.cancelEnrollment),'cancel'));
  }
  function wireProgramForm(editor){
    $('#cancelProgramForm',editor).onclick=()=>editor.innerHTML='';
    $('#camProgramForm',editor).onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget;const raw=formObject(form);const id=Number(form.dataset.programId)||null;const status=$('#programSaveStatus',form);const submit=$('button[type="submit"]',form);submit.disabled=true;status.textContent='Saving…';
      const payload={...raw,code:raw.code||null,description:raw.description||null,age_group:raw.age_group||null,skill_level:raw.skill_level||null,start_date:raw.start_date||null,end_date:raw.end_date||null};
      try{await requestJson(id?`/api/cam/programs/${id}`:'/api/cam/programs',{method:id?'PUT':'POST',body:JSON.stringify(payload)});notify(id?'Program updated.':'Program created.');await renderPrograms(true);}catch(err){status.textContent=err.message;submit.disabled=false;}
    };
  }
  function wireEnrollmentForm(editor){
    $('#cancelEnrollmentForm',editor).onclick=()=>editor.innerHTML='';
    $('#camEnrollmentForm',editor).onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget;const raw=formObject(form);const status=$('#enrollmentSaveStatus',form);const submit=$('button[type="submit"]',form);submit.disabled=true;status.textContent='Saving…';
      const payload={player_id:Number(raw.player_id),program_id:Number(raw.program_id),enrollment_type:raw.enrollment_type||'regular',start_date:raw.start_date||null,end_date:raw.end_date||null,notes:raw.notes||null};
      try{await requestJson('/api/cam/enrollments',{method:'POST',body:JSON.stringify(payload)});notify('Enrollment created.');await renderPrograms(true);}catch(err){status.textContent=err.message;submit.disabled=false;}
    };
  }
  function openEnrollmentAction(enrollments,id,action){
    const enrollment=enrollments.find(e=>Number(e.id)===id);const editor=$('#enrollmentEditor');if(!enrollment||!editor)return;
    editor.innerHTML=actionForm(enrollment,action);editor.scrollIntoView({behavior:'smooth',block:'start'});
    $('#cancelEnrollmentAction',editor).onclick=()=>editor.innerHTML='';
    $('#camEnrollmentActionForm',editor).onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget;const raw=formObject(form);const status=$('#enrollmentActionStatus',form);const submit=$('button[type="submit"]',form);submit.disabled=true;status.textContent='Saving…';
      const payload=action==='freeze'?{effective_date:raw.effective_date||null}:{effective_date:raw.effective_date||null,reason:raw.reason||null};
      try{await requestJson(`/api/cam/enrollments/${id}/${action}`,{method:'POST',body:JSON.stringify(payload)});notify(action==='freeze'?'Enrollment frozen.':'Enrollment cancelled.');await renderPrograms(true);}catch(err){status.textContent=err.message;submit.disabled=false;}
    };
  }
  function enhance(){
    scheduled=false;
    if(!$('#camWorkspace'))return;
    ensureTab();
    if(tabFromHash()==='programs')renderPrograms();
  }
  function schedule(){if(scheduled)return;scheduled=true;setTimeout(enhance,0);}
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
  window.addEventListener('hashchange',schedule);
  document.addEventListener('DOMContentLoaded',schedule);
  schedule();
})();
