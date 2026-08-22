(() => {
  const SESSION_KEY='cam-cam-session-v1';
  const qs=(s,r=document)=>r.querySelector(s);
  const qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  let applying=false;
  let generation=0;
  let reference={players:[],coaches:[],sessions:[]};
  let viewer=null;

  function route(){const raw=location.hash.replace(/^#/,'');const [page,query='']=raw.split('?');const p=new URLSearchParams(query);return{page:page||'dashboard',tab:p.get('tab')||'overview'};}
  function esc(v=''){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
  function token(){return sessionStorage.getItem(SESSION_KEY)||'';}
  function notify(message){if(typeof window.toast==='function')window.toast(message);else console.log(message);}
  async function request(url,options={}){
    const headers={'Content-Type':'application/json',...(options.headers||{})};
    if(token()&&!headers.Authorization)headers.Authorization=`Bearer ${token()}`;
    const response=await fetch(url,{cache:'no-store',...options,headers});
    let data=null;try{data=await response.json();}catch{}
    if(!response.ok){const error=new Error(data?.detail||`Request failed (${response.status})`);error.status=response.status;throw error;}
    return data;
  }
  function ensureTab(){
    const tabs=qs('#camWorkspace .cam-tabs');if(!tabs)return;
    let button=qs('[data-cam-reviews-tab]',tabs);
    if(!button){button=document.createElement('button');button.type='button';button.dataset.camReviewsTab='1';button.textContent='Player Reviews';button.onclick=()=>{location.hash='cam?tab=reviews';};tabs.appendChild(button);}
    if(route().page==='cam'&&route().tab==='reviews')qsa('button',tabs).forEach(btn=>btn.classList.toggle('active',btn===button));else button.classList.remove('active');
  }
  function scoreClass(score){return score>=4.5?'excellent':score>=3.5?'strong':score>=2.5?'developing':'focus';}
  function formatDate(v){if(!v)return'—';const d=new Date(`${String(v).slice(0,10)}T12:00:00`);return Number.isNaN(d.getTime())?esc(v):d.toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});}
  function roleLabel(role){return({owner:'Owner',admin:'Admin',coach:'Coach',parent:'Parent',player:'Player'})[role]||role;}

  function signInView(){return `<section class="cam-reviews-shell"><section class="cam-section-head"><div><span class="cam-kicker">PLAYER DEVELOPMENT · SECURE</span><h1>Player Reviews</h1><p>Coach evaluations and report cards are tied to Academy access. Sign in before viewing player-development records.</p></div></section><article class="panel cam-reviews-signin"><div class="cam-reviews-lock">🔒</div><div><h2>Academy sign-in required</h2><p>Owners and coaches can create reviews. Parents and players can see only published report cards linked to their account.</p></div><button id="reviewsGoAccess" class="primary">Go to Access & Roles</button></article></section>`;}

  function summary(reviews,canManage){
    const published=reviews.filter(r=>r.status==='published');
    const drafts=reviews.filter(r=>r.status==='draft');
    const avg=published.length?(published.reduce((a,r)=>a+Number(r.overall_score||0),0)/published.length).toFixed(2):'—';
    const open=reviews.reduce((n,r)=>n+(r.actions||[]).filter(a=>a.status==='open').length,0);
    return `<section class="cam-reviews-summary"><article><span>${canManage?'Reviews':'Report cards'}</span><strong>${reviews.length}</strong><small>${published.length} published</small></article><article><span>Average score</span><strong>${avg}</strong><small>Across published cards</small></article><article><span>Open actions</span><strong>${open}</strong><small>Development assignments</small></article><article><span>${canManage?'Drafts':'Latest'}</span><strong>${canManage?drafts.length:(published[0]?formatDate(published[0].review_date):'—')}</strong><small>${canManage?'Awaiting publish':'Published evaluation'}</small></article></section>`;
  }

  function scoreGrid(review){
    const items=[['Batting',review.batting_score],['Bowling',review.bowling_score],['Fielding',review.fielding_score],['Fitness',review.fitness_score]];
    return `<div class="cam-review-scores">${items.map(([label,score])=>`<div><span>${label}</span><strong class="${scoreClass(Number(score))}">${score}/5</strong><div class="cam-review-score-track"><i style="width:${Number(score)*20}%"></i></div></div>`).join('')}</div>`;
  }
  function actionList(review,canManage){
    const actions=review.actions||[];
    if(!actions.length)return '<div class="cam-review-no-actions">No assigned development actions.</div>';
    return `<div class="cam-review-actions">${actions.map(a=>`<div class="cam-review-action ${esc(a.status)}"><div><span>${esc(a.category)}</span><strong>${esc(a.title)}</strong>${a.detail?`<small>${esc(a.detail)}</small>`:''}${a.target_date?`<small>Target ${formatDate(a.target_date)}</small>`:''}</div>${canManage?`<button class="secondary" data-review-action="${a.id}" data-review-id="${review.id}" data-next-status="${a.status==='open'?'completed':'open'}">${a.status==='open'?'Mark complete':'Reopen'}</button>`:`<b>${a.status}</b>`}</div>`).join('')}</div>`;
  }
  function reviewCards(reviews,canManage){
    if(!reviews.length)return `<article class="panel cam-empty"><strong>${canManage?'No player reviews yet':'No published report cards yet'}</strong><span>${canManage?'Create a structured coach evaluation to begin the player-development history.':'Published coach evaluations will appear here.'}</span></article>`;
    return reviews.map(r=>`<article class="panel cam-review-card" data-review-card="${r.id}"><div class="cam-review-card-head"><div><span class="cam-review-status ${esc(r.status)}">${esc(r.status)}</span><h2>${esc(r.player_name)}</h2><p>${esc(r.period_label)} · ${formatDate(r.review_date)}${r.coach_name?` · Coach ${esc(r.coach_name)}`:''}</p></div><div class="cam-review-overall ${scoreClass(Number(r.overall_score))}"><span>Overall</span><strong>${Number(r.overall_score).toFixed(2)}</strong><small>/ 5</small></div></div>${scoreGrid(r)}<div class="cam-review-copy"><section><span>Coach summary</span><p>${esc(r.coach_summary)}</p></section>${r.strengths?`<section><span>Strengths</span><p>${esc(r.strengths)}</p></section>`:''}${r.focus_areas?`<section><span>Focus areas</span><p>${esc(r.focus_areas)}</p></section>`:''}${r.next_steps?`<section><span>Next steps</span><p>${esc(r.next_steps)}</p></section>`:''}</div><div class="cam-review-section-title"><strong>Development actions</strong><span>${(r.actions||[]).filter(a=>a.status==='open').length} open</span></div>${actionList(r,canManage)}${canManage&&r.status==='draft'?`<div class="cam-review-card-actions"><button class="primary" data-review-publish="${r.id}">Publish report card</button><small>Publishing makes this card visible to linked parent/player accounts and locks historical content.</small></div>`:''}</article>`).join('');
  }

  function formOptions(rows,label){return `<option value="">${label}</option>${rows.map(r=>`<option value="${r.id}">${esc(r.name||`${r.first_name||''} ${r.last_name||''}`.trim())}</option>`).join('')}`;}
  function sessionOptions(rows){return `<option value="">No session link</option>${rows.map(s=>`<option value="${s.id}">${formatDate(s.session_date)} · ${esc(s.start_time)}${s.batch_name?` · ${esc(s.batch_name)}`:` · ${esc(s.session_kind)}`}</option>`).join('')}`;}
  function createForm(){
    const isCoach=viewer?.role==='coach';
    const coachOptions=isCoach?reference.coaches.map(c=>`<option value="${c.id}" selected>${esc(`${c.first_name} ${c.last_name}`)}</option>`).join(''):formOptions(reference.coaches,'Select coach');
    return `<form id="camReviewForm" class="panel cam-review-form"><div class="panel-head"><div><span class="cam-kicker">NEW EVALUATION</span><h2>Create Player Review</h2><p>Score the four development pillars, record coaching insight, and assign a concrete next action.</p></div><button type="button" id="camReviewCancel" class="secondary">Cancel</button></div><div class="cam-review-form-grid"><label><span>Player</span><select name="player_id" required>${formOptions(reference.players,'Select player')}</select></label><label><span>Coach</span><select name="coach_id" required ${isCoach?'disabled':''}>${coachOptions}</select></label><label><span>Review date</span><input name="review_date" type="date" required value="${new Date().toISOString().slice(0,10)}"></label><label><span>Review type</span><select name="review_type"><option value="session">Session</option><option value="periodic">Periodic</option><option value="assessment">Assessment</option></select></label><label><span>Period / title</span><input name="period_label" required placeholder="August skill review"></label><label><span>Session link</span><select name="session_id">${sessionOptions(reference.sessions)}</select></label></div><div class="cam-review-score-inputs">${['batting','bowling','fielding','fitness'].map(k=>`<label><span>${k[0].toUpperCase()+k.slice(1)}</span><select name="${k}_score">${[1,2,3,4,5].map(n=>`<option value="${n}" ${n===3?'selected':''}>${n} / 5</option>`).join('')}</select></label>`).join('')}</div><div class="cam-review-form-grid cam-review-text-grid"><label><span>Strengths</span><textarea name="strengths" rows="3"></textarea></label><label><span>Focus areas</span><textarea name="focus_areas" rows="3"></textarea></label><label class="wide"><span>Coach summary</span><textarea name="coach_summary" required rows="4" placeholder="What changed, what was executed well, and what matters next?"></textarea></label><label class="wide"><span>Next steps</span><textarea name="next_steps" rows="3"></textarea></label><label><span>Action item</span><input name="action_title" placeholder="Front-foot decision drill"></label><label><span>Action category</span><select name="action_category"><option value="batting">Batting</option><option value="bowling">Bowling</option><option value="fielding">Fielding</option><option value="fitness">Fitness</option><option value="general">General</option></select></label></div><div class="cam-form-actions"><span>Saved initially as a staff-only draft.</span><button class="primary" type="submit">Save Draft Review</button></div></form>`;
  }

  function workspace(reviews){
    const canManage=['owner','admin','coach'].includes(viewer?.role)&&viewer?.permissions?.includes('reviews.manage');
    return `<section class="cam-reviews-shell"><section class="cam-section-head cam-reviews-head"><div><span class="cam-kicker">PLAYER DEVELOPMENT · REPORT CARDS</span><h1>Player Reviews</h1><p>Turn coach observations into a longitudinal player-development record with clear next actions.</p></div><div class="cam-reviews-viewer"><span>Viewing as</span><strong>${esc(viewer.display_name)}</strong><small>${esc(roleLabel(viewer.role))}</small>${canManage?'<button id="camNewReview" class="primary">＋ New Review</button>':''}</div></section>${summary(reviews,canManage)}<div id="camReviewComposer"></div><section id="camReviewList" class="cam-review-list">${reviewCards(reviews,canManage)}</section></section>`;
  }

  async function loadReviews(){return request('/api/cam/reviews');}
  function payloadFromForm(form){
    const fd=new FormData(form);const action=String(fd.get('action_title')||'').trim();
    const payload={player_id:Number(fd.get('player_id')),review_date:fd.get('review_date'),review_type:fd.get('review_type'),period_label:fd.get('period_label'),batting_score:Number(fd.get('batting_score')),bowling_score:Number(fd.get('bowling_score')),fielding_score:Number(fd.get('fielding_score')),fitness_score:Number(fd.get('fitness_score')),coach_summary:fd.get('coach_summary'),strengths:fd.get('strengths')||null,focus_areas:fd.get('focus_areas')||null,next_steps:fd.get('next_steps')||null,actions:action?[{category:fd.get('action_category'),title:action}]:[]};
    const sessionId=Number(fd.get('session_id')||0);if(sessionId)payload.session_id=sessionId;
    const coachId=viewer?.role==='coach'?Number(reference.coaches[0]?.id||0):Number(fd.get('coach_id')||0);if(coachId)payload.coach_id=coachId;
    return payload;
  }
  function wire(reviews){
    const canManage=['owner','admin','coach'].includes(viewer?.role)&&viewer?.permissions?.includes('reviews.manage');
    const newButton=qs('#camNewReview');if(newButton)newButton.onclick=()=>{const slot=qs('#camReviewComposer');slot.innerHTML=createForm();const form=qs('#camReviewForm');qs('#camReviewCancel').onclick=()=>{slot.innerHTML='';};form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('button[type="submit"]');button.disabled=true;try{await request('/api/cam/reviews',{method:'POST',body:JSON.stringify(payloadFromForm(form))});notify('Draft player review saved.');await renderReviews(true);}catch(error){notify(error.message);button.disabled=false;}};};
    qsa('[data-review-publish]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await request(`/api/cam/reviews/${button.dataset.reviewPublish}/publish`,{method:'POST',body:'{}'});notify('Report card published.');await renderReviews(true);}catch(error){notify(error.message);button.disabled=false;}});
    if(canManage)qsa('[data-review-action]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await request(`/api/cam/reviews/${button.dataset.reviewId}/actions/${button.dataset.reviewAction}`,{method:'PUT',body:JSON.stringify({status:button.dataset.nextStatus})});notify('Development action updated.');await renderReviews(true);}catch(error){notify(error.message);button.disabled=false;}});
  }
  async function renderReviews(force=false){
    if(route().page!=='cam'||route().tab!=='reviews')return;
    const content=qs('#camWorkspace .cam-content');if(!content)return;
    if(!force&&content.dataset.camReviewsOwned==='1')return;
    content.dataset.camReviewsOwned='1';const current=++generation;content.innerHTML='<div class="cam-reviews-loading">Loading player reviews…</div>';
    if(!token()){content.innerHTML=signInView();qs('#reviewsGoAccess').onclick=()=>{location.hash='cam?tab=access';};return;}
    try{viewer=await request('/api/auth/me');}catch(error){if(error.status===401){sessionStorage.removeItem(SESSION_KEY);content.innerHTML=signInView();qs('#reviewsGoAccess').onclick=()=>{location.hash='cam?tab=access';};return;}content.innerHTML=`<div class="cam-empty"><strong>Could not verify Academy access</strong><span>${esc(error.message)}</span></div>`;return;}
    if(current!==generation)return;
    const canManage=['owner','admin','coach'].includes(viewer.role)&&viewer.permissions?.includes('reviews.manage');
    try{if(canManage)reference=await request('/api/cam/reviews/reference');else reference={players:[],coaches:[],sessions:[]};const reviews=await loadReviews();if(current!==generation)return;content.innerHTML=workspace(reviews);wire(reviews);}catch(error){content.innerHTML=`<div class="cam-empty"><strong>Could not load player reviews</strong><span>${esc(error.message)}</span></div>`;}
  }
  function apply(){if(applying)return;applying=true;try{if(route().page!=='cam')return;ensureTab();if(route().tab==='reviews'){const content=qs('#camWorkspace .cam-content');if(content&&content.dataset.camReviewsOwned!=='1')setTimeout(()=>renderReviews(false),0);}}finally{applying=false;}}
  const observer=new MutationObserver(()=>apply());observer.observe(document.documentElement,{childList:true,subtree:true});window.addEventListener('hashchange',()=>setTimeout(apply,0));document.addEventListener('DOMContentLoaded',apply);apply();
})();
