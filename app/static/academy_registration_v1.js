(() => {
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  let rendering=false;
  let scheduled=false;
  let roleCache=null;
  let academyNameCache='Academy';

  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function route(){
    const raw=location.hash.replace(/^#/,'');const [page,query='']=raw.split('?');
    return {page:page||'dashboard',tab:new URLSearchParams(query).get('tab')||'overview'};
  }
  function registrationActive(){const r=route();return r.page==='academy'&&r.tab==='registration';}
  function dashboardActive(){const r=route();return r.page==='academy'&&r.tab==='overview';}
  function goRegistration(){location.hash='academy?tab=registration';}
  function notify(message){if(typeof window.toast==='function')window.toast(message);else console.log(message);}
  async function requestJson(url,options={}){
    const res=await fetch(url,{cache:'no-store',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    let data=null;try{data=await res.json();}catch{}
    if(!res.ok)throw new Error(data?.detail||`Request failed (${res.status})`);
    return data;
  }
  async function currentRole(){
    if(roleCache)return roleCache;
    try{const mode=await requestJson('/api/cam-mode');if(mode?.temporary_admin_mode){roleCache='admin';return roleCache;}}catch{}
    try{const me=await requestJson('/api/auth/me');roleCache=me?.role||'coach';}catch{roleCache='coach';}
    return roleCache;
  }
  async function registrationBranding(){
    try{return await requestJson('/api/academy/registration/branding');}
    catch{return {academy_name:'Academy'};}
  }
  function fmtDate(v){
    if(!v)return '—';const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);
    return new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(d);
  }
  function phoneDigits(v=''){return String(v||'').replace(/\D/g,'');}
  function statusLabel(v='created'){
    const map={created:'Link Created',sent:'Sent',opened:'Opened',in_progress:'In Progress',submitted:'Submitted',needs_information:'Needs Information',approved:'Approved',declined:'Declined',expired:'Expired',cancelled:'Cancelled'};
    return map[v]||v;
  }
  function formObject(form){const out={};new FormData(form).forEach((v,k)=>out[k]=typeof v==='string'?v.trim():v);return out;}
  function academyLabel(){
    const name=String(academyNameCache||'Academy').trim()||'Academy';
    return /academy$/i.test(name)?name:`${name} Academy`;
  }
  function shareMessage(item,url){
    const parent=[item.parent_first_name,item.parent_last_name].filter(Boolean).join(' ')||'Parent';
    return `Hi ${parent}, please complete the ${academyLabel()} player registration form using this secure link: ${url}`;
  }
  async function markSent(id,channel){
    try{await requestJson(`/api/academy/registration/invites/${id}/sent`,{method:'POST',body:JSON.stringify({channel})});}
    catch(err){console.warn('Could not mark registration sent',err);}
  }
  function showShare(item,url){
    const host=$('#registrationShareHost');if(!host)return;
    const message=shareMessage(item,url);const digits=phoneDigits(item.parent_phone);
    const whatsapp=`https://wa.me/${digits}?text=${encodeURIComponent(message)}`;
    const sms=`sms:${digits}?body=${encodeURIComponent(message)}`;
    const mailto=`mailto:${encodeURIComponent(item.parent_email||'')}?subject=${encodeURIComponent(`${academyLabel()} Player Registration`)}&body=${encodeURIComponent(message)}`;
    host.innerHTML=`<div class="cam-share-box"><strong>Registration link ready for ${esc(item.parent_first_name)} ${esc(item.parent_last_name)}</strong><div class="cam-share-url">${esc(url)}</div><div class="cam-share-actions"><button data-share="sms">Text Message</button><button data-share="whatsapp">WhatsApp</button>${item.parent_email?'<button data-share="email">Email</button>':''}<button data-share="copy">Copy Link</button></div></div>`;
    $('[data-share="sms"]',host)?.addEventListener('click',async()=>{await markSent(item.id,'sms');location.href=sms;});
    $('[data-share="whatsapp"]',host)?.addEventListener('click',async()=>{await markSent(item.id,'whatsapp');window.open(whatsapp,'_blank','noopener');});
    $('[data-share="email"]',host)?.addEventListener('click',async()=>{await markSent(item.id,'email');location.href=mailto;});
    $('[data-share="copy"]',host)?.addEventListener('click',async()=>{await navigator.clipboard.writeText(url);await markSent(item.id,'copy');notify('Registration link copied.');await renderRegistration(true);});
  }
  function kpi(label,value,note){return `<article class="cam-registration-kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></article>`;}
  function trackerRows(invites,role){
    if(!invites.length)return '<div class="cam-registration-empty"><strong>No registration links yet.</strong><div>Create the first registration link from the form on the left.</div></div>';
    return `<div class="cam-tracker-row header"><span>Parent</span><span>Sent By</span><span>Sent / Activity</span><span>Status</span><span>Player</span><span>Actions</span></div>`+invites.map(item=>{
      const canReview=(role==='owner'||role==='admin')&&item.application_id&&['submitted','needs_information','approved','declined'].includes(item.status);
      const canResend=['created','sent','opened','in_progress','needs_information','expired'].includes(item.status)&&!item.submitted_at;
      const canCancel=['created','sent','opened','in_progress','needs_information','expired'].includes(item.status)&&!item.submitted_at;
      const player=[item.player_first_name,item.player_last_name].filter(Boolean).join(' ')||'—';
      return `<div class="cam-tracker-row" data-invite-id="${item.id}"><div><strong>${esc(item.parent_first_name)} ${esc(item.parent_last_name)}</strong><small>${esc(item.parent_phone)}${item.parent_email?` · ${esc(item.parent_email)}`:''}</small></div><div><strong>${esc(item.sent_by_name||'Academy Staff')}</strong><small>${esc(item.sent_by_role||'')}</small></div><div><strong>${esc(fmtDate(item.sent_at||item.created_at))}</strong><small>Last: ${esc(fmtDate(item.last_activity_at||item.created_at))}</small></div><div><span class="cam-status ${esc(item.status)}">${esc(statusLabel(item.status))}</span></div><div><strong>${esc(player)}</strong><small>${item.application_id?`Application #${item.application_id}`:'Not submitted'}</small></div><div class="cam-row-actions">${canReview?`<button class="review" data-review-app="${item.application_id}">${item.status==='submitted'?'Review':'View'}</button>`:''}${canResend?`<button data-resend="${item.id}">Resend</button>`:''}${canCancel?`<button data-cancel="${item.id}">Cancel</button>`:''}</div></div>`;
    }).join('');
  }
  function pageHtml(invites,summary,role){
    const counts=summary?.counts||{};
    return `<section class="cam-registration-page"><section class="cam-registration-head"><div><span class="academy-kicker">STUDENT ONBOARDING · PROCESS 1</span><h1>Registration</h1><p>Create secure parent registration links, track progress through submission, and review completed applications before creating an active player.</p></div></section>
      <section class="cam-registration-kpis">${kpi('Submitted',summary?.submitted||0,'Needs Admin/Owner review')}${kpi('Waiting on Parent',summary?.waiting_on_parent||0,'Sent, opened, or in progress')}${kpi('In Progress',summary?.in_progress||0,'Parent started the form')}${kpi('Approved',summary?.approved||0,'Converted to player records')}</section>
      <section class="cam-registration-grid"><article class="panel cam-registration-compose"><h2>Send Registration Link</h2><p>Enter the parent contact. The parent completes all player and registration details.</p><form id="registrationInviteForm"><div class="cam-registration-fields"><label><span>Parent First Name *</span><input name="parent_first_name" required maxlength="100"></label><label><span>Parent Last Name *</span><input name="parent_last_name" required maxlength="100"></label><label class="wide"><span>Mobile Number *</span><input name="parent_phone" type="tel" required maxlength="60" placeholder="404-555-1234"></label><label class="wide"><span>Email</span><input name="parent_email" type="email" maxlength="200" placeholder="Optional"></label></div><div class="cam-registration-actions"><button class="primary" type="submit">Create Registration Link</button></div></form><div id="registrationShareHost"></div></article>
      <article class="panel cam-registration-tracker"><h2>Registration Tracking</h2><p>${invites.length} registration record${invites.length===1?'':'s'} visible to your role.</p><div class="cam-tracker-table">${trackerRows(invites,role)}</div></article></section><div id="registrationReviewHost"></div></section>`;
  }
  function reviewField(label,value){return `<dt>${esc(label)}</dt><dd>${esc(value||'—')}</dd>`;}
  function contactText(contact){return contact?`${contact.first_name||''} ${contact.last_name||''} · ${contact.relationship||''} · ${contact.phone||''}`.replace(/\s+·\s*$/,''):'—';}
  function reviewHtml(app){
    const emergency=app.emergency_contacts||[];
    return `<article class="panel cam-registration-review"><div class="cam-registration-head"><div><span class="academy-kicker">APPLICATION #${app.id}</span><h2>${esc(app.player_first_name)} ${esc(app.player_last_name)}</h2><p>Submitted ${esc(fmtDate(app.submitted_at))} · Status: ${esc(statusLabel(app.status))}</p></div><button type="button" class="secondary" id="closeRegistrationReview">Close</button></div>
      <section class="cam-review-summary"><div><span>Cricket Role</span><strong>${esc(app.cricket_role||'—')}</strong></div><div><span>Batting / Bowling</span><strong>${esc(app.batting_order||'—')} · ${esc(app.bowling_type||'—')}</strong></div><div><span>Wicketkeeping</span><strong>${app.wicketkeeping===true?'Yes':app.wicketkeeping===false?'No':'—'}</strong></div></section>
      <section class="cam-review-sections"><article class="cam-review-section"><h3>Player</h3><dl>${reviewField('Name',`${app.player_first_name||''} ${app.player_last_name||''}`)}${reviewField('Date of Birth',app.player_date_of_birth)}${reviewField('Gender',app.player_gender)}${reviewField('Role',app.cricket_role)}${reviewField('Batting Order',app.batting_order)}${reviewField('Bowling Type',app.bowling_type)}</dl></article>
      <article class="cam-review-section"><h3>Parent</h3><dl>${reviewField('Name',`${app.parent_first_name||''} ${app.parent_last_name||''}`)}${reviewField('Relationship',app.parent_relationship)}${reviewField('Email',app.parent_email)}${reviewField('Phone',app.parent_phone)}${reviewField('Address',[app.parent_address_line1,app.parent_city,app.parent_state,app.parent_postal_code,app.parent_country].filter(Boolean).join(', '))}</dl></article>
      <article class="cam-review-section"><h3>Safety Contacts</h3><dl>${reviewField('Emergency 1',contactText(emergency[0]))}${reviewField('Emergency 2',contactText(emergency[1]))}${reviewField('Guardian',app.guardian_same_as_parent?'Same as primary parent':contactText(app.guardian))}</dl></article>
      <article class="cam-review-section medical"><h3>Restricted Medical Information</h3><dl>${reviewField('Injuries',app.injuries)}${reviewField('Surgeries',app.surgeries)}${reviewField('Medical',app.medical_considerations)}${reviewField('Allergies',app.allergies)}${reviewField('Restrictions',app.physical_restrictions)}</dl></article></section>
      <article class="cam-review-section" style="margin-top:12px"><h3>Other Notes</h3><div>${esc(app.additional_notes||'No additional notes.')}</div>${app.review_note?`<div class="review-note" style="margin-top:10px"><strong>Previous review note:</strong> ${esc(app.review_note)}</div>`:''}</article>
      ${app.status==='approved'?`<div class="cam-review-actions"><button id="openApprovedPlayer" class="primary" data-player-id="${app.approved_player_id}">Open Player</button></div>`:app.status==='declined'?'<div class="cam-review-actions"><span class="cam-status declined">Declined</span></div>':`<div class="cam-review-note"><label for="registrationReviewNote">Admin note / information request</label><textarea id="registrationReviewNote" rows="3" placeholder="Optional note to parent"></textarea></div><div class="cam-review-actions"><button class="danger" data-review-action="decline">Decline</button><button class="warn" data-review-action="needs_information">Request Information</button><button class="primary" data-review-action="approve">Approve & Create Player</button></div>`}</article>`;
  }
  async function renderRegistration(force=false){
    if(!registrationActive()||rendering)return;
    const content=$('#academyWorkspace .academy-content');if(!content)return;
    if(!force&&content.dataset.registrationRendered==='1')return;
    rendering=true;content.dataset.registrationRendered='loading';content.innerHTML='<div class="panel academy-loading">Loading registration pipeline…</div>';
    try{
      const [invites,summary,role,branding]=await Promise.all([requestJson('/api/academy/registration/invites'),requestJson('/api/academy/registration/summary'),currentRole(),registrationBranding()]);
      academyNameCache=String(branding?.academy_name||'Academy').trim()||'Academy';
      if(!registrationActive())return;
      content.innerHTML=pageHtml(Array.isArray(invites)?invites:[],summary||{},role);
      content.dataset.registrationRendered='1';wirePage(Array.isArray(invites)?invites:[],role);
    }catch(err){content.innerHTML=`<div class="warning">${esc(err.message)}</div>`;content.dataset.registrationRendered='1';}
    finally{rendering=false;}
  }
  function wirePage(invites,role){
    $('#registrationInviteForm')?.addEventListener('submit',async e=>{
      e.preventDefault();const form=e.currentTarget;const raw=formObject(form);const submit=$('button[type="submit"]',form);submit.disabled=true;submit.textContent='Creating…';
      try{const item=await requestJson('/api/academy/registration/invites',{method:'POST',body:JSON.stringify(raw)});showShare(item,item.registration_url);notify('Registration link created.');form.reset();}
      catch(err){notify(err.message);}finally{submit.disabled=false;submit.textContent='Create Registration Link';}
    });
    $$('[data-resend]').forEach(btn=>btn.onclick=async()=>{
      btn.disabled=true;try{const item=await requestJson(`/api/academy/registration/invites/${btn.dataset.resend}/resend`,{method:'POST',body:'{}'});showShare(item,item.registration_url);notify('New registration link generated.');await renderRegistration(true);}catch(err){notify(err.message);}finally{btn.disabled=false;}
    });
    $$('[data-cancel]').forEach(btn=>btn.onclick=async()=>{
      if(!confirm('Cancel this registration link?'))return;btn.disabled=true;try{await requestJson(`/api/academy/registration/invites/${btn.dataset.cancel}/cancel`,{method:'POST',body:'{}'});notify('Registration link cancelled.');await renderRegistration(true);}catch(err){notify(err.message);}finally{btn.disabled=false;}
    });
    if(role==='owner'||role==='admin')$$('[data-review-app]').forEach(btn=>btn.onclick=()=>openReview(Number(btn.dataset.reviewApp)));
  }
  async function openReview(applicationId){
    const host=$('#registrationReviewHost');if(!host)return;host.innerHTML='<article class="panel cam-registration-review">Loading application…</article>';host.scrollIntoView({behavior:'smooth',block:'start'});
    try{const app=await requestJson(`/api/academy/registration/applications/${applicationId}`);host.innerHTML=reviewHtml(app);wireReview(host,app);}
    catch(err){host.innerHTML=`<div class="warning">${esc(err.message)}</div>`;}
  }
  function wireReview(host,app){
    $('#closeRegistrationReview',host)?.addEventListener('click',()=>host.innerHTML='');
    $('#openApprovedPlayer',host)?.addEventListener('click',()=>{location.hash='academy?tab=players';});
    $$('[data-review-action]',host).forEach(btn=>btn.onclick=async()=>{
      const action=btn.dataset.reviewAction;const note=$('#registrationReviewNote',host)?.value.trim()||null;
      if(action==='approve'&&!confirm('Approve this application and create the active player/guardian records?'))return;
      btn.disabled=true;
      try{const result=await requestJson(`/api/academy/registration/applications/${app.id}/review`,{method:'POST',body:JSON.stringify({action,note})});notify(action==='approve'?'Registration approved and player created.':action==='needs_information'?'Information request recorded.':'Registration declined.');await renderRegistration(true);if(result?.id){} }
      catch(err){notify(err.message);btn.disabled=false;}
    });
  }
  async function injectDashboardCard(){
    if(!dashboardActive())return;
    const stats=$('#academyWorkspace .academy-stats');if(!stats||$('.cam-registration-dashboard-card',stats))return;
    try{
      const summary=await requestJson('/api/academy/registration/summary');if(!dashboardActive()||!stats.isConnected)return;
      const card=document.createElement('article');card.className='academy-stat blue cam-registration-dashboard-card';card.tabIndex=0;card.setAttribute('role','button');
      card.innerHTML=`<div class="academy-stat-icon">✎</div><div><span>Submitted Applications</span><strong>${Number(summary?.submitted||0)}</strong><small>${Number(summary?.waiting_on_parent||0)} waiting on parent · Open Registration</small></div>`;
      card.onclick=goRegistration;card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();goRegistration();}};stats.appendChild(card);
    }catch(err){console.warn('Registration dashboard summary unavailable',err);}
  }
  function apply(){scheduled=false;if(registrationActive())renderRegistration();else if(dashboardActive())injectDashboardCard();}
  function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(apply);}
  window.addEventListener('hashchange',()=>{roleCache=null;schedule();});
  document.addEventListener('DOMContentLoaded',schedule);
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
  schedule();
})();
