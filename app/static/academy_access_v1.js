(() => {
  const SESSION_KEY = 'cam-academy-session-v1';
  const qs = (s, r=document) => r.querySelector(s);
  const qsa = (s, r=document) => [...r.querySelectorAll(s)];
  let applying = false;
  let generation = 0;

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    const params=new URLSearchParams(query);
    return {page:page||'dashboard',tab:params.get('tab')||'overview'};
  }
  function esc(value=''){
    return String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function token(){ return sessionStorage.getItem(SESSION_KEY)||''; }
  function saveToken(value){
    if(value) sessionStorage.setItem(SESSION_KEY,value); else sessionStorage.removeItem(SESSION_KEY);
  }
  function notify(message){
    if(typeof window.toast==='function') window.toast(message); else console.log(message);
  }
  async function request(url, options={}){
    const headers={'Content-Type':'application/json',...(options.headers||{})};
    if(token() && !headers.Authorization) headers.Authorization=`Bearer ${token()}`;
    const response=await fetch(url,{cache:'no-store',...options,headers});
    let data=null; try{data=await response.json();}catch{}
    if(!response.ok){
      const err=new Error(data?.detail||`Request failed (${response.status})`);
      err.status=response.status;
      throw err;
    }
    return data;
  }

  function ensureTab(){
    const tabs=qs('#academyWorkspace .academy-tabs');
    if(!tabs) return;
    let button=qs('[data-academy-access-tab]',tabs);
    if(!button){
      button=document.createElement('button');
      button.type='button';
      button.dataset.academyAccessTab='1';
      button.textContent='Access & Roles';
      button.onclick=()=>{location.hash='academy?tab=access';};
      tabs.appendChild(button);
    }
    const active=route().page==='academy'&&route().tab==='access';
    qsa('button',tabs).forEach(btn=>btn.classList.toggle('active',btn===button&&active ? true : btn!==button&&btn.classList.contains('active')&&!active));
    if(active){
      qsa('button',tabs).forEach(btn=>btn.classList.toggle('active',btn===button));
    }
  }

  function roleLabel(role){
    return ({owner:'Owner',admin:'Admin',coach:'Coach',parent:'Parent',player:'Player'})[role]||role;
  }
  function permissionLabel(permission){
    return permission.replaceAll('.', ' · ').replaceAll('_',' ');
  }
  function statusPill(status){return `<span class="academy-access-status ${esc(status)}">${esc(status)}</span>`;}

  function loginView(status){
    if(!status.has_users){
      return `<section class="academy-access-shell">
        <section class="academy-section-head"><div><span class="academy-kicker">SECURITY FOUNDATION · FIRST RUN</span><h1>Access & Roles</h1><p>Create the first owner account. The bootstrap token is read only for this one request and is never saved in the browser.</p></div></section>
        <article class="panel academy-access-auth-card">
          <div><h2>Bootstrap Academy Owner</h2><p>${status.bootstrap_configured?'Bootstrap is configured on the server.':'Server setup is incomplete: configure CAM_BOOTSTRAP_TOKEN first.'}</p></div>
          <form id="academyBootstrapForm" class="academy-access-form">
            <label><span>Display name</span><input name="display_name" required minlength="2" autocomplete="name"></label>
            <label><span>Email</span><input name="email" type="email" required autocomplete="username"></label>
            <label><span>Password</span><input name="password" type="password" required minlength="10" autocomplete="new-password"></label>
            <label><span>Bootstrap token</span><input name="bootstrap_token" type="password" required autocomplete="off"></label>
            <button class="primary" type="submit" ${status.bootstrap_configured?'':'disabled'}>Create Owner Account</button>
          </form>
        </article>
      </section>`;
    }
    return `<section class="academy-access-shell">
      <section class="academy-section-head"><div><span class="academy-kicker">SECURITY FOUNDATION</span><h1>Access & Roles</h1><p>Sign in to manage Academy identities and role-based access.</p></div></section>
      <article class="panel academy-access-auth-card">
        <div><h2>Academy Sign In</h2><p>Sessions are stored only in this browser tab and expire on the server.</p></div>
        <form id="academyLoginForm" class="academy-access-form">
          <label><span>Email</span><input name="email" type="email" required autocomplete="username"></label>
          <label><span>Password</span><input name="password" type="password" required autocomplete="current-password"></label>
          <button class="primary" type="submit">Sign In</button>
        </form>
      </article>
    </section>`;
  }

  function userRows(users){
    if(!users.length) return `<div class="academy-empty"><strong>No access users</strong><span>Create the first staff or family account.</span></div>`;
    return users.map(user=>`<div class="academy-access-user-row" data-access-user="${user.id}">
      <div class="academy-access-avatar">${esc(String(user.display_name||user.email).split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase())}</div>
      <div class="academy-access-user-copy"><strong>${esc(user.display_name)}</strong><small>${esc(user.email)}</small><small>${user.linked_name?`Linked: ${esc(user.linked_name)}`:'No linked Academy identity'}</small></div>
      <span class="academy-access-role ${esc(user.role)}">${esc(roleLabel(user.role))}</span>
      ${statusPill(user.status)}
      <div class="academy-access-user-meta"><small>Last login</small><strong>${user.last_login_at?esc(new Date(user.last_login_at).toLocaleString()):'Never'}</strong></div>
    </div>`).join('');
  }

  function roleCards(roles){
    return roles.map(row=>`<article class="academy-access-role-card"><div><span class="academy-access-role ${esc(row.role)}">${esc(roleLabel(row.role))}</span><strong>${row.permissions.length} permissions</strong></div><div class="academy-access-permissions">${row.permissions.map(p=>`<span>${esc(permissionLabel(p))}</span>`).join('')}</div></article>`).join('');
  }

  function auditRows(rows){
    if(!rows.length) return `<div class="academy-empty"><strong>No access activity yet</strong></div>`;
    return rows.slice(0,25).map(row=>`<div class="academy-access-audit-row"><div><strong>${esc(row.action.replaceAll('_',' '))}</strong><small>${esc(row.actor_name||'System')}${row.target_name?` → ${esc(row.target_name)}`:''}</small></div><span>${esc(new Date(row.created_at).toLocaleString())}</span></div>`).join('');
  }

  function linkOptions(reference, role, selected=''){
    let rows=[];
    if(role==='coach') rows=(reference.coaches||[]).map(x=>[x.id,`${x.first_name} ${x.last_name}`]);
    if(role==='parent') rows=(reference.guardians||[]).map(x=>[x.id,`${x.first_name} ${x.last_name}`]);
    if(role==='player') rows=(reference.players||[]).map(x=>[x.id,x.name]);
    if(!rows.length) return '<option value="">No link required / available</option>';
    return `<option value="">No linked identity yet</option>${rows.map(([id,name])=>`<option value="${id}" ${String(id)===String(selected)?'selected':''}>${esc(name)}</option>`).join('')}`;
  }

  function adminView(me, users, roles, reference, audit){
    return `<section class="academy-access-shell">
      <section class="academy-section-head academy-access-head"><div><span class="academy-kicker">SECURITY FOUNDATION · RBAC</span><h1>Access & Roles</h1><p>Manage who can enter the Academy workspace and what each role is allowed to do.</p></div><div class="academy-access-session"><span>Signed in as</span><strong>${esc(me.display_name)}</strong><small>${esc(roleLabel(me.role))}</small><button id="academyAccessLogout" class="secondary">Sign Out</button></div></section>
      <section class="academy-access-summary">
        <article><span>Active users</span><strong>${users.filter(x=>x.status==='active').length}</strong><small>${users.length} total accounts</small></article>
        <article><span>Staff access</span><strong>${users.filter(x=>['owner','admin','coach'].includes(x.role)).length}</strong><small>Owner, admin and coach</small></article>
        <article><span>Family access</span><strong>${users.filter(x=>['parent','player'].includes(x.role)).length}</strong><small>Parent and player</small></article>
        <article><span>Roles</span><strong>${roles.length}</strong><small>Permission templates</small></article>
      </section>
      <section class="academy-access-grid">
        <article class="panel academy-access-users-panel"><div class="panel-head"><div><h2>Access Users</h2><p>Accounts can optionally link directly to a coach, guardian or player record.</p></div><button id="academyAddAccessUser" class="primary">＋ Add User</button></div><div id="academyAccessEditor"></div><div class="academy-access-users">${userRows(users)}</div></article>
        <aside class="academy-access-side"><article class="panel"><div class="panel-head"><div><h2>Role Matrix</h2><p>Foundation permissions for the next enforcement phase.</p></div></div><div class="academy-access-role-grid">${roleCards(roles)}</div></article></aside>
      </section>
      <article class="panel academy-access-audit"><div class="panel-head"><div><h2>Security Audit Trail</h2><p>Recent account, sign-in and password-management activity.</p></div></div>${auditRows(audit)}</article>
      <script type="application/json" id="academyAccessReference">${esc(JSON.stringify(reference))}</script>
    </section>`;
  }

  function memberView(me){
    return `<section class="academy-access-shell">
      <section class="academy-section-head academy-access-head"><div><span class="academy-kicker">YOUR ACADEMY ACCESS</span><h1>Access & Roles</h1><p>Your account is active. Administrative user management is reserved for Academy owners and admins.</p></div><div class="academy-access-session"><span>Signed in as</span><strong>${esc(me.display_name)}</strong><small>${esc(roleLabel(me.role))}</small><button id="academyAccessLogout" class="secondary">Sign Out</button></div></section>
      <section class="academy-access-member-card panel"><span class="academy-access-role ${esc(me.role)}">${esc(roleLabel(me.role))}</span><h2>${esc(me.display_name)}</h2><p>${me.linked_name?`Linked Academy identity: ${esc(me.linked_name)}`:'This account is not yet linked to a specific Academy identity.'}</p><div class="academy-access-permissions">${(me.permissions||[]).map(p=>`<span>${esc(permissionLabel(p))}</span>`).join('')}</div></section>
    </section>`;
  }

  function editorForm(reference){
    return `<form id="academyAccessUserForm" class="academy-access-editor">
      <div class="academy-access-editor-head"><div><span class="academy-kicker">NEW ACCESS USER</span><h3>Create account</h3></div><button type="button" id="academyCancelAccessUser" class="secondary">Cancel</button></div>
      <div class="academy-access-form-grid">
        <label><span>Display name</span><input name="display_name" required minlength="2"></label>
        <label><span>Email</span><input name="email" type="email" required></label>
        <label><span>Temporary password</span><input name="password" type="password" required minlength="10"></label>
        <label><span>Role</span><select name="role"><option value="admin">Admin</option><option value="coach">Coach</option><option value="parent">Parent</option><option value="player">Player</option></select></label>
        <label class="academy-access-link-field"><span>Linked identity</span><select name="linked_id">${linkOptions(reference,'admin')}</select></label>
      </div>
      <div class="academy-form-actions"><span id="academyAccessSaveStatus"></span><button class="primary" type="submit">Create Access User</button></div>
    </form>`;
  }

  function parseReference(){
    const node=qs('#academyAccessReference');
    if(!node) return {coaches:[],guardians:[],players:[]};
    try{return JSON.parse(node.textContent);}catch{return {coaches:[],guardians:[],players:[]};}
  }

  function wireLogin(status){
    const bootstrap=qs('#academyBootstrapForm');
    if(bootstrap){
      bootstrap.onsubmit=async event=>{
        event.preventDefault();
        const form=new FormData(bootstrap);
        const button=bootstrap.querySelector('button[type="submit"]');
        button.disabled=true;
        try{
          const result=await request('/api/auth/bootstrap',{
            method:'POST',
            headers:{'X-CAM-Bootstrap':String(form.get('bootstrap_token')||'')},
            body:JSON.stringify({display_name:form.get('display_name'),email:form.get('email'),password:form.get('password')})
          });
          saveToken(result.token); notify('Owner account created.'); await renderAccess();
        }catch(error){notify(error.message);}
        finally{button.disabled=false;}
      };
      return;
    }
    const login=qs('#academyLoginForm');
    if(login){
      login.onsubmit=async event=>{
        event.preventDefault();
        const form=new FormData(login);
        const button=login.querySelector('button[type="submit"]');
        button.disabled=true;
        try{
          const result=await request('/api/auth/login',{method:'POST',body:JSON.stringify({email:form.get('email'),password:form.get('password')})});
          saveToken(result.token); notify('Signed in.'); await renderAccess();
        }catch(error){notify(error.message);}
        finally{button.disabled=false;}
      };
    }
  }

  function wireAuthenticated(me){
    const logout=qs('#academyAccessLogout');
    if(logout) logout.onclick=async()=>{
      try{await request('/api/auth/logout',{method:'POST'});}catch{}
      saveToken(''); notify('Signed out.'); await renderAccess();
    };
    if(!['owner','admin'].includes(me.role)) return;
    const add=qs('#academyAddAccessUser');
    if(add) add.onclick=()=>{
      const editor=qs('#academyAccessEditor');
      const reference=parseReference();
      editor.innerHTML=editorForm(reference);
      qs('#academyCancelAccessUser').onclick=()=>{editor.innerHTML='';};
      const form=qs('#academyAccessUserForm');
      const role=form.elements.role;
      const link=form.elements.linked_id;
      const refreshLink=()=>{link.innerHTML=linkOptions(reference,role.value);};
      role.onchange=refreshLink; refreshLink();
      form.onsubmit=async event=>{
        event.preventDefault();
        const fd=new FormData(form);
        const selected=fd.get('linked_id')?Number(fd.get('linked_id')):null;
        const payload={display_name:fd.get('display_name'),email:fd.get('email'),password:fd.get('password'),role:fd.get('role'),status:'active'};
        if(payload.role==='coach') payload.coach_id=selected;
        if(payload.role==='parent') payload.guardian_id=selected;
        if(payload.role==='player') payload.player_id=selected;
        const button=form.querySelector('button[type="submit"]'); button.disabled=true;
        try{await request('/api/academy/access/users',{method:'POST',body:JSON.stringify(payload)});notify('Access user created.');await renderAccess();}
        catch(error){notify(error.message);button.disabled=false;}
      };
    };
  }

  async function renderAccess(){
    if(route().page!=='academy'||route().tab!=='access') return;
    const myGeneration=++generation;
    ensureTab();
    const content=qs('#academyWorkspace .academy-content');
    if(!content) return;
    content.innerHTML='<div class="academy-access-loading">Loading access controls…</div>';
    let statusData;
    try{statusData=await request('/api/auth/bootstrap-status',{headers:{}});}catch(error){content.innerHTML=`<div class="academy-empty"><strong>Access service unavailable</strong><span>${esc(error.message)}</span></div>`;return;}
    if(myGeneration!==generation) return;
    if(!token()){
      content.innerHTML=loginView(statusData); wireLogin(statusData); return;
    }
    let me;
    try{me=await request('/api/auth/me');}
    catch(error){
      if(error.status===401){saveToken('');content.innerHTML=loginView(statusData);wireLogin(statusData);return;}
      throw error;
    }
    if(!['owner','admin'].includes(me.role)){
      content.innerHTML=memberView(me); wireAuthenticated(me); return;
    }
    try{
      const [users,roles,reference,audit]=await Promise.all([
        request('/api/academy/access/users'),request('/api/academy/access/roles'),request('/api/academy/access/reference'),request('/api/academy/access/audit?limit=50')
      ]);
      if(myGeneration!==generation) return;
      content.innerHTML=adminView(me,users,roles,reference,audit); wireAuthenticated(me);
    }catch(error){
      content.innerHTML=`<div class="academy-empty"><strong>Could not load access controls</strong><span>${esc(error.message)}</span></div>`;
    }
  }

  function apply(){
    if(applying) return;
    applying=true;
    try{
      if(route().page!=='academy') return;
      ensureTab();
      if(route().tab==='access') setTimeout(renderAccess,0);
    } finally { applying=false; }
  }

  const observer=new MutationObserver(()=>apply());
  observer.observe(document.documentElement,{childList:true,subtree:true});
  window.addEventListener('hashchange',()=>setTimeout(apply,0));
  document.addEventListener('DOMContentLoaded',apply);
  apply();
})();
