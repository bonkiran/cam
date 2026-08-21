(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const GROUPS = ['Beginners', 'U11', 'U13', 'U14', 'U15'];
  let scheduled = false;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    return {page: page || 'dashboard', tab: new URLSearchParams(query).get('tab') || 'overview'};
  }

  function active() {
    const r = route();
    return r.page === 'academy' && r.tab === 'players';
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

  function groupForBatch(batch = {}) {
    const text = `${batch.name || ''} ${batch.code || ''} ${batch.program_name || ''}`.toUpperCase();
    if (/\bU15\b/.test(text)) return 'U15';
    if (/\bU14\b/.test(text)) return 'U14';
    if (/\bU13\b/.test(text)) return 'U13';
    if (/\bU11\b/.test(text)) return 'U11';
    if (/BEGINNER/.test(text)) return 'Beginners';
    return null;
  }

  function playerName(row) {
    return $('strong', row)?.textContent?.trim() || `Player ${row?.dataset?.playerId || ''}`;
  }

  async function rosterData() {
    const groups = Object.fromEntries(GROUPS.map(name => [name, new Set()]));
    const assigned = new Set();
    const batches = await requestJson('/api/academy/batches');
    const relevant = (Array.isArray(batches) ? batches : [])
      .map(batch => ({batch, group: groupForBatch(batch)}))
      .filter(item => item.group);

    const rosters = await Promise.all(relevant.map(async item => {
      try {
        const rows = await requestJson(`/api/academy/batches/${Number(item.batch.id)}/players`);
        return {group:item.group, rows:Array.isArray(rows) ? rows : []};
      } catch (error) {
        console.warn(`Could not load ${item.group} roster`, error);
        return {group:item.group, rows:[]};
      }
    }));

    rosters.forEach(({group, rows}) => {
      rows.forEach(row => {
        if (String(row.status || 'active').toLowerCase() !== 'active') return;
        const playerId = Number(row.player_id || 0);
        if (!playerId) return;
        groups[group].add(playerId);
        assigned.add(playerId);
      });
    });

    const assignableBatches = relevant
      .filter(item => String(item.batch.status || 'active').toLowerCase() === 'active')
      .map(item => ({...item.batch, c17_group:item.group}))
      .sort((a, b) => {
        const groupOrder = GROUPS.indexOf(a.c17_group) - GROUPS.indexOf(b.c17_group);
        if (groupOrder !== 0) return groupOrder;
        return String(a.name || '').localeCompare(String(b.name || ''));
      });

    return {groups, assigned, assignableBatches};
  }

  function batchPanel(name) {
    const panel = document.createElement('article');
    panel.className = 'panel c17-player-batch-panel';
    panel.dataset.playerBatch = name;
    panel.innerHTML = `<div class="c17-player-batch-head"><div><h3>${name}</h3><p>Players currently assigned to this batch.</p></div><strong class="c17-player-batch-count">0</strong></div><div class="c17-player-batch-list"></div>`;
    return panel;
  }

  function assignmentForm(page, data, selectedPlayerId = null) {
    const rows = $$('.c17-unassigned-list .academy-player-row[data-player-id]', page)
      .sort((a, b) => playerName(a).localeCompare(playerName(b)));
    const playerOptions = rows.map(row => {
      const id = Number(row.dataset.playerId || 0);
      return `<option value="${id}" ${id === Number(selectedPlayerId) ? 'selected' : ''}>${esc(playerName(row))}</option>`;
    }).join('');
    const batchOptions = data.assignableBatches.map(batch => {
      const label = batch.name && String(batch.name).toUpperCase() !== String(batch.c17_group).toUpperCase()
        ? `${batch.c17_group} · ${batch.name}`
        : batch.c17_group;
      return `<option value="${Number(batch.id)}">${esc(label)}</option>`;
    }).join('');

    return `<form id="c17AssignPlayerForm" class="panel academy-form-card c17-player-assign-form">
      <div class="academy-form-title"><div><span class="academy-kicker">PLAYER ASSIGNMENT</span><h2>Assign Player to Batch</h2><p>Select an unassigned player and the active batch they should join.</p></div><button type="button" class="secondary" data-close-player-assignment>Cancel</button></div>
      <div class="academy-form-grid two">
        <label class="academy-field"><span>Player *</span><select name="player_id" required>${playerOptions}</select></label>
        <label class="academy-field"><span>Batch *</span><select name="batch_id" required>${batchOptions}</select></label>
      </div>
      <div class="academy-form-actions"><span id="c17PlayerAssignStatus"></span><button type="submit" class="primary">Assign Player</button></div>
    </form>`;
  }

  function refreshCounters(page) {
    let assignedTotal = 0;
    GROUPS.forEach(name => {
      const panel = $(`.c17-player-batch-panel[data-player-batch="${name}"]`, page);
      if (!panel) return;
      const count = $$('.academy-player-row[data-player-id]', panel).length;
      assignedTotal += count;
      const badge = $('.c17-player-batch-count', panel);
      if (badge) badge.textContent = String(count);
      const list = $('.c17-player-batch-list', panel);
      const empty = $('.c17-player-batch-empty', list);
      if (count && empty) empty.remove();
      if (!count && list && !empty) list.innerHTML = '<div class="c17-player-batch-empty">No players assigned.</div>';
    });

    const unassignedList = $('.c17-unassigned-list', page);
    const unassignedCount = unassignedList ? $$('.academy-player-row[data-player-id]', unassignedList).length : 0;
    const unassignedBadge = $('.c17-unassigned-count', page);
    if (unassignedBadge) unassignedBadge.textContent = String(unassignedCount);
    if (unassignedList) {
      const empty = $('.c17-unassigned-empty', unassignedList);
      if (unassignedCount && empty) empty.remove();
      if (!unassignedCount && !empty) unassignedList.innerHTML = '<div class="c17-unassigned-empty">All active players are assigned to a batch.</div>';
    }

    const summary = $('.c17-player-records-summary', page);
    if (summary) summary.textContent = `${assignedTotal} player${assignedTotal === 1 ? '' : 's'} assigned across Beginners, U11, U13, U14 and U15.`;

    const assignTop = $('#assignAcademyPlayer', page);
    if (assignTop) assignTop.disabled = unassignedCount === 0;
  }

  function moveAssignedPlayer(page, data, playerId, batchId) {
    const row = $(`.c17-unassigned-list .academy-player-row[data-player-id="${Number(playerId)}"]`, page);
    const batch = data.assignableBatches.find(item => Number(item.id) === Number(batchId));
    if (!row || !batch) return;

    $('[data-assign-player]', row)?.remove();
    row.classList.remove('c17-unassigned-player-row');
    const target = $(`.c17-player-batch-panel[data-player-batch="${batch.c17_group}"] .c17-player-batch-list`, page);
    if (target) {
      $('.c17-player-batch-empty', target)?.remove();
      target.appendChild(row);
    }
    refreshCounters(page);
  }

  function openAssignmentEditor(page, data, selectedPlayerId = null) {
    const editor = $('#playerEditor', page);
    if (!editor) return;
    const rows = $$('.c17-unassigned-list .academy-player-row[data-player-id]', page);
    if (!rows.length) {
      notify('All active players are already assigned to a batch.');
      return;
    }
    if (!data.assignableBatches.length) {
      notify('No active Beginners, U11, U13, U14 or U15 batch is available for assignment.');
      return;
    }

    editor.innerHTML = assignmentForm(page, data, selectedPlayerId);
    $('[data-close-player-assignment]', editor)?.addEventListener('click', () => { editor.innerHTML = ''; });
    const form = $('#c17AssignPlayerForm', editor);
    if (!form) return;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const playerId = Number(form.elements.player_id.value || 0);
      const batchId = Number(form.elements.batch_id.value || 0);
      const status = $('#c17PlayerAssignStatus', form);
      const submit = $('button[type="submit"]', form);
      if (!playerId || !batchId) {
        if (status) status.textContent = 'Select both a player and a batch.';
        return;
      }
      if (submit) submit.disabled = true;
      if (status) status.textContent = 'Assigning…';
      try {
        await requestJson(`/api/academy/batches/${batchId}/players`, {
          method:'POST',
          body:JSON.stringify({player_id:playerId, waitlist_if_full:false, joined_on:new Date().toISOString().slice(0,10)})
        });
        moveAssignedPlayer(page, data, playerId, batchId);
        editor.innerHTML = '';
        notify('Player assigned to batch.');
      } catch (error) {
        if (status) status.textContent = error.message;
        if (submit) submit.disabled = false;
      }
    });
    editor.scrollIntoView({behavior:'smooth', block:'start'});
  }

  async function decorate(content) {
    if (!active() || !content?.isConnected) return;
    if ($('.c17-players-page', content)) return;
    const legacyPanel = $('.academy-player-panel', content);
    if (!legacyPanel || content.dataset.c17PlayersDecorating === '1') return;

    content.dataset.c17PlayersDecorating = '1';
    content.style.visibility = 'hidden';

    const legacyRows = $$('.academy-player-row[data-player-id]', legacyPanel);
    const addButton = $('#addAcademyPlayer', content);
    const editor = $('#playerEditor', content);

    try {
      const [heroMarkup, data] = await Promise.all([
        window.C17AcademyHeader?.hero
          ? window.C17AcademyHeader.hero({title:'Players', subtitle:'C17 Academy Players'})
          : Promise.resolve('<section class="c17-hero c17-page-hero"><div class="c17-welcome"><h1>Players</h1><p>C17 Academy Players</p></div></section>'),
        rosterData()
      ]);

      if (!active() || !content.isConnected) return;

      const rowById = new Map(legacyRows.map(row => [Number(row.dataset.playerId || 0), row]));
      const renderedAssigned = new Set();
      const page = document.createElement('section');
      page.className = 'c17-players-page';
      page.innerHTML = `${heroMarkup}<div class="c17-player-editor-host"></div><section class="c17-player-records"><div class="c17-player-records-head"><div><h2>Player Records</h2><p class="c17-player-records-summary"></p></div><div class="c17-player-add-host"></div></div><div class="c17-player-batch-grid"></div></section><section class="panel c17-unassigned-panel"><div class="c17-unassigned-head"><div><h2>Unassigned Players</h2><p>Active players who are not currently assigned to Beginners, U11, U13, U14 or U15.</p></div><strong class="c17-unassigned-count">0</strong></div><div class="c17-unassigned-list"></div></section>`;

      if (editor) $('.c17-player-editor-host', page).appendChild(editor);
      const actionHost = $('.c17-player-add-host', page);
      if (addButton) actionHost.appendChild(addButton);
      const assignButton = document.createElement('button');
      assignButton.type = 'button';
      assignButton.className = 'secondary';
      assignButton.id = 'assignAcademyPlayer';
      assignButton.textContent = '＋ Assign Player';
      actionHost.appendChild(assignButton);

      const grid = $('.c17-player-batch-grid', page);
      GROUPS.forEach(name => {
        const panel = batchPanel(name);
        const list = $('.c17-player-batch-list', panel);
        const ids = [...data.groups[name]].filter(id => rowById.has(id));
        ids.sort((a, b) => playerName(rowById.get(a)).localeCompare(playerName(rowById.get(b))));
        ids.forEach(id => {
          if (renderedAssigned.has(id)) return;
          renderedAssigned.add(id);
          list.appendChild(rowById.get(id));
        });
        $('.c17-player-batch-count', panel).textContent = String(ids.filter(id => renderedAssigned.has(id)).length);
        if (!list.children.length) list.innerHTML = '<div class="c17-player-batch-empty">No players assigned.</div>';
        grid.appendChild(panel);
      });

      const unassignedList = $('.c17-unassigned-list', page);
      const unassignedRows = legacyRows
        .filter(row => !data.assigned.has(Number(row.dataset.playerId || 0)))
        .sort((a, b) => playerName(a).localeCompare(playerName(b)));
      unassignedRows.forEach(row => {
        row.classList.add('c17-unassigned-player-row');
        const actions = $('.academy-row-actions', row) || row.appendChild(document.createElement('div'));
        actions.classList.add('academy-row-actions');
        const assign = document.createElement('button');
        assign.type = 'button';
        assign.className = 'secondary c17-assign-row-button';
        assign.dataset.assignPlayer = String(Number(row.dataset.playerId || 0));
        assign.textContent = 'Assign';
        actions.appendChild(assign);
        unassignedList.appendChild(row);
      });

      content.replaceChildren(page);
      content.dataset.c17PlayersRendered = '1';
      refreshCounters(page);

      $('#assignAcademyPlayer', page)?.addEventListener('click', () => openAssignmentEditor(page, data));
      $$('[data-assign-player]', page).forEach(button => {
        button.addEventListener('click', () => openAssignmentEditor(page, data, Number(button.dataset.assignPlayer)));
      });
    } catch (error) {
      console.error('Could not build C17 Players page', error);
    } finally {
      if (content?.isConnected) {
        content.style.visibility = '';
        delete content.dataset.c17PlayersDecorating;
      }
    }
  }

  function apply() {
    scheduled = false;
    if (!active()) return;
    const content = $('#academyWorkspace .academy-content');
    if (!content) return;
    if ($('.c17-players-page', content)) return;
    if ($('.academy-player-panel', content)) decorate(content);
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(apply);
  }

  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(() => {
    if (!active()) return;
    const content = $('#academyWorkspace .academy-content');
    if (content && !$('.c17-players-page', content) && $('.academy-player-panel', content)) decorate(content);
  }).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
