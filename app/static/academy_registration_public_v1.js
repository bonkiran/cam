(() => {
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  const token=decodeURIComponent(location.pathname.split('/').filter(Boolean).pop()||'');
  let loaded=null;
  let saveTimer=null;
  let saving=false;
  let queued=false;

  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  async function request(url,options={}){
    const res=await fetch(url,{cache:'no-store',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    let data=null;try{data=await res.json();}catch{}
    if(!res.ok)throw new Error(data?.detail||`Request failed (${res.status})`);
    return data;
  }
  function value(name){return $(`[name="${name}"]`)?.value.trim()||null;}
  function boolRadio(name){const checked=$(`[name="${name}"]:checked`);if(!checked)return null;return checked.value==='yes';}
  function contactFrom(root,attr){
    const out={};
    $$(`[${attr}]`,root).forEach(el=>{
      const key=el.getAttribute(attr);
      out[key]=el.type==='checkbox'?!!el.checked:(el.value.trim()||null);
    });
    return out;
  }
  function payload(){
    const guardianSame=$('#guardianSameAsParent').checked;
    return {
      player_first_name:value('player_first_name'),player_last_name:value('player_last_name'),
      player_date_of_birth:value('player_date_of_birth'),player_gender:value('player_gender'),
      cricket_role:value('cricket_role'),batting_order:value('batting_order'),bowling_type:value('bowling_type'),
      wicketkeeping:boolRadio('wicketkeeping'),
      parent_first_name:value('parent_first_name'),parent_last_name:value('parent_last_name'),
      parent_relationship:value('parent_relationship'),parent_email:value('parent_email'),parent_phone:value('parent_phone'),
      parent_address_line1:value('parent_address_line1'),parent_address_line2:value('parent_address_line2'),
      parent_city:value('parent_city'),parent_state:value('parent_state'),parent_postal_code:value('parent_postal_code'),
      parent_country:value('parent_country'),
      emergency_contacts:$$('[data-emergency]').map(card=>contactFrom(card,'data-contact')),
      guardian_same_as_parent:guardianSame,
      guardian:guardianSame?null:contactFrom($('#guardianFields'),'data-guardian'),
      injuries:value('injuries'),surgeries:value('surgeries'),medical_considerations:value('medical_considerations'),
      allergies:value('allergies'),physical_restrictions:value('physical_restrictions'),additional_notes:value('additional_notes'),
      consent_confirmed:!!$('[name="consent_confirmed"]')?.checked,
    };
  }
  function setField(name,val){const el=$(`[name="${name}"]`);if(el&&val!==null&&val!==undefined)el.value=String(val);}
  function setContact(root,attr,data={}){
    $$(`[${attr}]`,root).forEach(el=>{
      const key=el.getAttribute(attr);const val=data?.[key];
      if(el.type==='checkbox')el.checked=val===undefined?true:!!val;else if(val!==null&&val!==undefined)el.value=String(val);
    });
  }
  function fill(data){
    const app=data?.application||{};
    [
      'player_first_name','player_last_name','player_date_of_birth','player_gender','cricket_role','batting_order','bowling_type',
      'parent_first_name','parent_last_name','parent_relationship','parent_email','parent_phone','parent_address_line1','parent_address_line2',
      'parent_city','parent_state','parent_postal_code','parent_country','injuries','surgeries','medical_considerations','allergies','physical_restrictions','additional_notes'
    ].forEach(name=>setField(name,app[name]));
    if(app.wicketkeeping===true)$('[name="wicketkeeping"][value="yes"]').checked=true;
    if(app.wicketkeeping===false)$('[name="wicketkeeping"][value="no"]').checked=true;
    const emergency=app.emergency_contacts||[];
    $$('[data-emergency]').forEach((card,index)=>setContact(card,'data-contact',emergency[index]||{}));
    $('#guardianSameAsParent').checked=app.guardian_same_as_parent!==false;
    updateGuardianVisibility();
    if(app.guardian)setContact($('#guardianFields'),'data-guardian',app.guardian);
    $('[name="consent_confirmed"]').checked=!!app.consent_confirmed;
    if(app.review_note){const note=$('#reviewNote');note.hidden=false;note.innerHTML=`<strong>Academy requested more information:</strong><br>${esc(app.review_note)}`;}
    const invite=data?.invite||{};
    $('#inviteParentName').textContent=[invite.parent_first_name,invite.parent_last_name].filter(Boolean).join(' ')||'Parent';
    $('#inviteSentBy').textContent=invite.sent_by_name?`Link sent by ${invite.sent_by_name}`:'';
    if(!app.parent_first_name)setField('parent_first_name',invite.parent_first_name);
    if(!app.parent_last_name)setField('parent_last_name',invite.parent_last_name);
    if(!app.parent_phone)setField('parent_phone',invite.parent_phone);
    if(!app.parent_email)setField('parent_email',invite.parent_email);
  }
  function updateGuardianVisibility(){
    const same=$('#guardianSameAsParent').checked;
    $('#guardianFields').hidden=same;
    $$('[data-guardian="first_name"],[data-guardian="last_name"],[data-guardian="relationship"],[data-guardian="phone"]').forEach(el=>el.required=!same);
  }
  function draftStatus(text){const el=$('#draftStatus');if(el)el.textContent=text;}
  function scheduleSave(){
    clearTimeout(saveTimer);draftStatus('Unsaved changes…');
    saveTimer=setTimeout(saveDraft,700);
  }
  async function saveDraft(){
    if(saving){queued=true;return;}
    saving=true;queued=false;draftStatus('Saving…');
    try{await request(`/api/public/registration/${encodeURIComponent(token)}/draft`,{method:'PUT',body:JSON.stringify(payload())});draftStatus('Saved automatically.');}
    catch(err){draftStatus(`Could not save: ${err.message}`);}
    finally{saving=false;if(queued)saveDraft();}
  }
  function wireAutosave(){
    $('#registrationForm').addEventListener('input',scheduleSave);
    $('#registrationForm').addEventListener('change',scheduleSave);
    $('#guardianSameAsParent').addEventListener('change',()=>{updateGuardianVisibility();scheduleSave();});
  }
  async function load(){
    if(!token){showError('The registration link is incomplete.');return;}
    try{
      loaded=await request(`/api/public/registration/${encodeURIComponent(token)}`);
      const terminal=loaded?.invite?.status;
      if(terminal==='submitted'||terminal==='approved'){
        $('#registrationLoading').hidden=true;$('#registrationSuccess').hidden=false;return;
      }
      fill(loaded);
      $('#registrationLoading').hidden=true;$('#registrationForm').hidden=false;
      wireAutosave();
      $('#registrationForm').onsubmit=submit;
    }catch(err){showError(err.message);}
  }
  function showError(message){
    $('#registrationLoading').hidden=true;$('#registrationForm').hidden=true;$('#registrationError').hidden=false;$('#registrationErrorText').textContent=message;
  }
  async function submit(event){
    event.preventDefault();
    const form=event.currentTarget;
    if(!form.reportValidity())return;
    const button=$('#submitRegistration');button.disabled=true;button.textContent='Submitting…';draftStatus('Submitting registration…');
    try{
      await request(`/api/public/registration/${encodeURIComponent(token)}/submit`,{method:'POST',body:JSON.stringify(payload())});
      form.hidden=true;$('#registrationSuccess').hidden=false;window.scrollTo({top:0,behavior:'smooth'});
    }catch(err){button.disabled=false;button.textContent='Submit Registration';draftStatus(err.message);}
  }
  load();
})();
