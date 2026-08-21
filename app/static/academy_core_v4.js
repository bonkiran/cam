(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  let renderToken = 0;
  let activeTab = null;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    return { page: page || 'dashboard', tab: new URLSearchParams(query).get('tab') || 'overview' };
  }

  function academyActive() {
    return route().page === 'academy';
  }

  function esc(value = '') {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function notify(message) {
    if (typeof window.toast === 'function') window.toast(message);
    else console.log(message);
  }

  async function requestJson(url, options = {}) {
    const headers = {...(options.headers || {})};
    if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    const response = await fetch(url, {cache:'no-store', ...options, headers});
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    return data;
  }

  function ensureBaseShell() {
    const app = $('#app');
    if (!app) return null;
    let main = $('.main', app);
    if (!main && typeof window.shell === 'function') {
      app.innerHTML = window.shell('', 'academy');
      if (typeof window.wireShell === 'function') window.wireShell('academy');
      main = $('.main', app);
    }
    return main;
  }

  function ensureWorkspace() {
    const main = ensureBaseShell();
    if (!main) return null;
    let workspace = $('#academyWorkspace', main);
    if (workspace) return workspace;

    const topbar = $('.topbar', main);
    [...main.children].forEach(child => {
      if (child !== topbar) child.remove();
    });

    workspace = document.createElement('div');
    workspace.id = 'academyWorkspace';
    workspace.innerHTML = '<div class="academy-content" data-core-route=""></div>';
    main.appendChild(workspace);
    return workspace;
  }

  function freshContent(tab) {
    const workspace = ensureWorkspace();
    if (!workspace) return null;
    const current = $('.academy-content', workspace);
    if (current && current.dataset.coreRoute === tab) return current;

    const next = document.createElement('div');
    next.className = 'academy-content';
    next.dataset.coreRoute = tab;
    next.setAttribute('aria-live', 'polite');
    next.innerHTML = '<div class="c17-route-loading" aria-busy="true">Loading…</div>';
    if (current) current.replaceWith(next);
    else workspace.appendChild(next);
    return next;
  }

  function field(label, name, value = '', type = 'text', required = false, placeholder = '') {
    return `<label class="academy-field"><span>${esc(label)}${required?' *':''}</span><input type="${esc(type)}" name="${esc(name)}" value="${esc(value || '')}" ${required?'required':''} placeholder="${esc(placeholder)}"></label>`;
  }

  function selectField(label, name, value, options) {
    return `<label class="academy-field"><span>${esc(label)}</span><select name="${esc(name)}"><option value="">Select</option>${options.map(option => `<option value="${esc(option)}" ${String(value || '') === String(option) ? 'selected' : ''}>${esc(option)}</option>`).join('')}</select></label>`;
  }

  function textArea(label, name, value = '') {
    return `<label class="academy-field academy-field-wide"><span>${esc(label)}</span><textarea name="${esc(name)}" rows="3">${esc(value || '')}</textarea></label>`;
  }

  function setupMarkup(profile = {}) {
    return `<section class="academy-section-head"><div><span class="academy-kicker">ACADEMY PROFILE</span><h1>Settings</h1><p>Maintain the academy identity, contact information, primary location and timezone.</p></div></section>
      <form id="academyProfileForm" class="panel academy-form-card">
        <div class="academy-form-section"><div><h2>Academy Information</h2><p>Core organization and contact information.</p></div><div class="academy-form-grid two">
          ${field('Academy Name','name',profile.name,'text',true)}${field('Email','email',profile.email,'email')}${field('Phone','phone',profile.phone)}${field('Website','website',profile.website,'url')}
        </div></div>
        <div class="academy-form-section"><div><h2>Primary Location</h2><p>Primary academy address and local timezone.</p></div><div class="academy-form-grid two">
          ${field('Address Line 1','address_line1',profile.address_line1)}${field('Address Line 2','address_line2',profile.address_line2)}${field('City','city',profile.city)}${field('State / Province','state',profile.state)}${field('ZIP / Postal Code','postal_code',profile.postal_code)}${field('Country','country',profile.country || 'United States')}${field('Timezone','timezone',profile.timezone || 'America/New_York')}
        </div></div>
        <div class="academy-form-actions"><span id="academySaveStatus"></span><button type="submit" class="primary">Save Academy Profile</button></div>
      </form>`;
  }

  function guardianMarkup(guardian = {}, index = 0) {
    return `<div class="guardian-card" data-guardian-card data-guardian-id="${esc(guardian.id || '')}">
      <div class="guardian-card-head"><div><strong>Guardian ${index + 1}</strong><small>Parent/guardian, billing and pickup contact.</small></div><button type="button" class="danger guardian-remove">Remove</button></div>
      <div class="academy-form-grid two">
        ${field('First Name','guardian_first_name',guardian.first_name,'text',true)}${field('Last Name','guardian_last_name',guardian.last_name,'text',true)}
        ${field('Relationship','guardian_relationship',guardian.relationship,'text',false,'Mother, Father, Guardian…')}${field('Phone','guardian_phone',guardian.phone)}${field('Email','guardian_email',guardian.email,'email')}
      </div>
      <div class="guardian-flags">
        <label><input type="checkbox" name="guardian_is_primary" ${guardian.is_primary?'checked':''}> Primary guardian</label>
        <label><input type="checkbox" name="guardian_billing_contact" ${guardian.billing_contact?'checked':''}> Billing contact</label>
        <label><input type="checkbox" name="guardian_pickup_authorized" ${guardian.pickup_authorized===0||guardian.pickup_authorized===false?'':'checked'}> Authorized pickup</label>
      </div>
    </div>`;
  }

  function playerFormMarkup(player = {}) {
    const guardians = player.guardians || [];
    const editing = Boolean(player.id);
    return `<form id="academyPlayerForm" class="panel academy-form-card" data-player-id="${esc(player.id || '')}">
      <div class="academy-form-title"><div><span class="academy-kicker">${editing?'EDIT PLAYER':'NEW PLAYER'}</span><h2>${editing?'Update Player':'Add Player'}</h2><p>Maintain the player and guardian record used throughout academy operations.</p></div><button type="button" class="secondary" id="cancelPlayerForm">Cancel</button></div>
      <div class="academy-form-section"><div><h2>Player Information</h2><p>Identity and academy status.</p></div><div class="academy-form-grid three">
        ${field('Full Display Name','name',player.name,'text',true)}${field('First Name','first_name',player.first_name)}${field('Last Name','last_name',player.last_name)}${field('Preferred Name','preferred_name',player.preferred_name)}${field('Date of Birth','date_of_birth',player.date_of_birth,'date')}${selectField('Gender','gender',player.gender,['Female','Male','Non-binary','Prefer not to say'])}${field('Joined On','joined_on',player.joined_on,'date')}${selectField('Status','status',player.status || 'active',['active','inactive','waitlisted'])}
      </div></div>
      <div class="academy-form-section"><div><h2>Cricket Profile</h2><p>Initial cricket characteristics.</p></div><div class="academy-form-grid three">
        ${selectField('Batting Style','batting_style',player.batting_style,['Right-handed','Left-handed'])}${field('Bowling Style','bowling_style',player.bowling_style,'text',false,'Right-arm fast, leg spin…')}${selectField('Handedness','handedness',player.handedness,['Right','Left'])}${selectField('Skill Level','skill_level',player.skill_level,['Beginner','Developing','Intermediate','Advanced','Elite'])}
      </div></div>
      <div class="academy-form-section"><div><h2>Player Contact & Address</h2></div><div class="academy-form-grid three">
        ${field('Email','email',player.email,'email')}${field('Phone','phone',player.phone)}${field('Address Line 1','address_line1',player.address_line1)}${field('Address Line 2','address_line2',player.address_line2)}${field('City','city',player.city)}${field('State','state',player.state)}${field('ZIP / Postal Code','postal_code',player.postal_code)}${field('Country','country',player.country)}
      </div></div>
      <div class="academy-form-section"><div><h2>Emergency Contact</h2></div><div class="academy-form-grid two">${field('Emergency Contact Name','emergency_contact_name',player.emergency_contact_name)}${field('Emergency Contact Phone','emergency_contact_phone',player.emergency_contact_phone)}</div></div>
      <div class="academy-form-section"><div class="academy-section-row"><div><h2>Parents / Guardians</h2><p>Add one or more guardian contacts.</p></div><button type="button" class="secondary" id="addGuardian">＋ Add Guardian</button></div><div id="guardianList" class="guardian-list">${guardians.map((guardian, index) => guardianMarkup(guardian, index)).join('')}</div></div>
      <div class="academy-form-section"><div><h2>Internal Notes</h2></div><div class="academy-form-grid">${textArea('Notes','notes',player.notes)}</div></div>
      <div class="academy-form-actions"><span id="playerSaveStatus"></span><button type="submit" class="primary">${editing?'Save Changes':'Create Player'}</button></div>
    </form>`;
  }

  function playerRows(players) {
    if (!players.length) return '<div class="academy-empty"><strong>No academy players yet</strong><span>Add the first player to begin.</span></div>';
    return players.map(player => {
      const initials = String(player.name || '?').split(/\s+/).map(x => x[0]).join('').slice(0,2).toUpperCase();
      const primary = (player.guardians || []).find(g => Number(g.is_primary) === 1) || (player.guardians || [])[0];
      const secondary = [player.skill_level, player.batting_style].filter(Boolean).join(' · ') || 'Cricket profile not completed';
      return `<div class="academy-player-row detailed" data-player-id="${Number(player.id)}"><div class="academy-avatar">${esc(initials)}</div><div><strong>${esc(player.name)}</strong><small>${esc(secondary)}</small><small>${primary?`Guardian: ${esc(primary.first_name)} ${esc(primary.last_name)}${primary.phone?` · ${esc(primary.phone)}`:''}`:'Guardian not added'}</small></div><span class="academy-status ${esc(player.status || 'active')}">${esc(player.status || 'active')}</span><div class="academy-row-actions"><button data-edit-player="${Number(player.id)}">Edit</button></div></div>`;
    }).join('');
  }

  function playersMarkup(players) {
    return `<section class="academy-section-head"><div><span class="academy-kicker">PLAYER DIRECTORY</span><h1>Players</h1><p>Create and maintain player, cricket, emergency and guardian information.</p></div><button class="primary" id="addAcademyPlayer">＋ Add Player</button></section>
      <div id="playerEditor"></div>
      <article class="panel academy-player-panel"><div class="panel-head"><div><h2>Player Records</h2><p>${players.length} total player${players.length===1?'':'s'}.</p></div></div><div class="academy-player-list">${playerRows(players)}</div></article>`;
  }

  function formObject(form) {
    const out = {};
    new FormData(form).forEach((value, key) => out[key] = typeof value === 'string' ? value.trim() : value);
    return out;
  }

  function collectGuardians(root) {
    return $$('[data-guardian-card]', root).map(card => ({
      id: Number(card.dataset.guardianId) || null,
      first_name: $('[name="guardian_first_name"]', card)?.value.trim() || '',
      last_name: $('[name="guardian_last_name"]', card)?.value.trim() || '',
      relationship: $('[name="guardian_relationship"]', card)?.value.trim() || null,
      email: $('[name="guardian_email"]', card)?.value.trim() || null,
      phone: $('[name="guardian_phone"]', card)?.value.trim() || null,
      is_primary: Boolean($('[name="guardian_is_primary"]', card)?.checked),
      billing_contact: Boolean($('[name="guardian_billing_contact"]', card)?.checked),
      pickup_authorized: Boolean($('[name="guardian_pickup_authorized"]', card)?.checked),
    })).filter(g => g.first_name || g.last_name);
  }

  function wireGuardians(root) {
    $$('.guardian-remove', root).forEach(button => button.onclick = () => {
      button.closest('[data-guardian-card]')?.remove();
      $$('[data-guardian-card]', root).forEach((card, index) => {
        const title = $('.guardian-card-head strong', card);
        if (title) title.textContent = `Guardian ${index + 1}`;
      });
    });
  }

  async function openPlayerEditor(playerId = null) {
    if (route().tab !== 'players') return;
    const content = $('#academyWorkspace .academy-content');
    const target = $('#playerEditor', content);
    if (!target) return;
    target.innerHTML = '<div class="panel academy-loading">Loading player…</div>';
    try {
      const player = playerId ? await requestJson(`/api/academy/players/${playerId}`) : {};
      if (route().tab !== 'players' || !target.isConnected) return;
      target.innerHTML = playerFormMarkup(player);
      $('#cancelPlayerForm', target).onclick = () => { target.innerHTML = ''; };
      $('#addGuardian', target).onclick = () => {
        const list = $('#guardianList', target);
        const count = $$('[data-guardian-card]', list).length;
        list.insertAdjacentHTML('beforeend', guardianMarkup({}, count));
        wireGuardians(target);
      };
      wireGuardians(target);
      $('#academyPlayerForm', target).onsubmit = savePlayer;
    } catch (error) {
      target.innerHTML = `<div class="warning">${esc(error.message)}</div>`;
    }
  }

  async function savePlayer(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const raw = formObject(form);
    const id = Number(form.dataset.playerId) || null;
    const payload = {
      name: raw.name,
      first_name: raw.first_name || null,
      last_name: raw.last_name || null,
      preferred_name: raw.preferred_name || null,
      date_of_birth: raw.date_of_birth || null,
      gender: raw.gender || null,
      batting_style: raw.batting_style || null,
      bowling_style: raw.bowling_style || null,
      handedness: raw.handedness || null,
      skill_level: raw.skill_level || null,
      email: raw.email || null,
      phone: raw.phone || null,
      address_line1: raw.address_line1 || null,
      address_line2: raw.address_line2 || null,
      city: raw.city || null,
      state: raw.state || null,
      postal_code: raw.postal_code || null,
      country: raw.country || null,
      emergency_contact_name: raw.emergency_contact_name || null,
      emergency_contact_phone: raw.emergency_contact_phone || null,
      joined_on: raw.joined_on || null,
      status: raw.status || 'active',
      notes: raw.notes || null,
      guardians: collectGuardians(form),
    };
    const status = $('#playerSaveStatus', form);
    const submit = $('button[type="submit"]', form);
    submit.disabled = true;
    if (status) status.textContent = 'Saving…';
    try {
      await requestJson(id ? `/api/academy/players/${id}` : '/api/academy/players', {method:id?'PUT':'POST', body:JSON.stringify(payload)});
      notify(id ? 'Player updated.' : 'Player created.');
      await renderCoreRoute(true);
    } catch (error) {
      if (status) status.textContent = error.message;
      submit.disabled = false;
    }
  }

  async function renderSetup(content, token) {
    try {
      const data = await requestJson('/api/academy/profile');
      if (token !== renderToken || route().tab !== 'setup' || !content.isConnected) return;
      content.innerHTML = setupMarkup(data?.profile || data || {});
      const form = $('#academyProfileForm', content);
      if (form) form.onsubmit = async event => {
        event.preventDefault();
        const status = $('#academySaveStatus', form);
        const submit = $('button[type="submit"]', form);
        submit.disabled = true;
        if (status) status.textContent = 'Saving…';
        try {
          await requestJson('/api/academy/profile', {method:'PUT', body:JSON.stringify(formObject(form))});
          notify('Academy profile saved.');
          await renderCoreRoute(true);
        } catch (error) {
          if (status) status.textContent = error.message;
          submit.disabled = false;
        }
      };
    } catch (error) {
      content.innerHTML = `<div class="warning">${esc(error.message)}</div>`;
    }
  }

  async function renderPlayers(content, token) {
    try {
      const players = await requestJson('/api/academy/players');
      if (token !== renderToken || route().tab !== 'players' || !content.isConnected) return;
      content.innerHTML = playersMarkup(Array.isArray(players) ? players : []);
      $('#addAcademyPlayer', content)?.addEventListener('click', () => openPlayerEditor());
      $$('[data-edit-player]', content).forEach(button => button.onclick = () => openPlayerEditor(Number(button.dataset.editPlayer)));
    } catch (error) {
      content.innerHTML = `<div class="warning">${esc(error.message)}</div>`;
    }
  }

  async function renderCoreRoute(force = false) {
    if (!academyActive()) return;
    const current = route();
    if (!force && activeTab === current.tab && $('#academyWorkspace .academy-content')) return;
    activeTab = current.tab;
    const token = ++renderToken;
    const content = force ? (() => {
      const workspace = ensureWorkspace();
      const old = $('.academy-content', workspace);
      const next = document.createElement('div');
      next.className = 'academy-content';
      next.dataset.coreRoute = current.tab;
      next.innerHTML = '<div class="c17-route-loading" aria-busy="true">Loading…</div>';
      old?.replaceWith(next);
      return next;
    })() : freshContent(current.tab);
    if (!content) return;

    if (current.tab === 'setup') await renderSetup(content, token);
    else if (current.tab === 'players') await renderPlayers(content, token);
    // Dashboard, Registration, Programs, Coaches, Finance, Reports, and other
    // feature routes are owned by their focused modules. The clean content root
    // above is intentionally left for that single route owner to populate.
  }

  function onRouteChange() {
    if (!academyActive()) {
      activeTab = null;
      renderToken += 1;
      return;
    }
    renderCoreRoute(false);
  }

  window.C17_ACADEMY_CORE = 'v4';
  window.addEventListener('hashchange', onRouteChange);
  document.addEventListener('DOMContentLoaded', onRouteChange);
  onRouteChange();
})();
