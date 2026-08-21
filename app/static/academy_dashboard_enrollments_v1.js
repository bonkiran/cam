(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  let scheduled = false;
  let loading = false;
  let enrollmentCache = null;
  let enrollmentCachedAt = 0;
  let batchCache = null;
  let batchCachedAt = 0;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    return {page: page || 'dashboard', tab: new URLSearchParams(query).get('tab') || 'overview'};
  }

  function active() {
    const current = route();
    return current.page === 'academy' && current.tab === 'overview';
  }

  function esc(value = '') {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function notify(message) {
    if (typeof window.toast === 'function') window.toast(message);
    else console.log(message);
  }

  function dateLabel(value) {
    if (!value) return '—';
    const date = new Date(`${String(value).slice(0, 10)}T12:00:00`);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'});
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      cache:'no-store',
      ...options,
      headers:{'Content-Type':'application/json', ...(options.headers || {})},
    });
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    return data;
  }

  async function loadEnrollments() {
    const now = Date.now();
    if (enrollmentCache && now - enrollmentCachedAt < 15000) return enrollmentCache;
    enrollmentCache = await requestJson('/api/academy/dashboard/new-player-enrollments');
    enrollmentCachedAt = now;
    return enrollmentCache || {count:0, players:[]};
  }

  async function loadBatches() {
    const now = Date.now();
    if (batchCache && now - batchCachedAt < 15000) return batchCache;
    const rows = await requestJson('/api/academy/batches');
    batchCache = Array.isArray(rows) ? rows : [];
    batchCachedAt = now;
    return batchCache;
  }

  function existingRegistrationPanel(content) {
    const title = $$('h1,h2,h3,h4,strong,b,span,div', content).find(node => {
      if (node.children.length) return false;
      const text = (node.textContent || '').trim();
      return text === 'New Player Registrations' || text.startsWith('New Player Registrations:');
    });
    return title?.closest('article,.panel,section') || null;
  }

  function placementMarkup(player) {
    if (!player.batch_id) {
      return `<button type="button" class="secondary cam-assign-batch" data-player-id="${esc(player.player_id)}">Assign Batch</button>`;
    }
    const label = player.batch_status === 'waitlisted' ? 'Waitlisted' : 'Assigned';
    return `<span class="cam-batch-assigned ${esc(player.batch_status || 'active')}">${esc(label)} · ${esc(player.batch_name || 'Batch')}</span>`;
  }

  function rowsMarkup(players = []) {
    if (!players.length) {
      return '<div class="academy-dash-empty">No players have completed enrollment this month.</div>';
    }
    return players.map(player => `
      <div class="academy-dash-session cam-new-enrollment-row" data-enrollment-id="${esc(player.enrollment_id)}" data-player-id="${esc(player.player_id)}">
        <div class="cam-new-enrollment-player">
          <strong>${esc(player.player_name || 'Player')}</strong>
          <small>Enrollment complete</small>
        </div>
        <div class="cam-new-enrollment-actions">
          <span>Enrolled ${esc(dateLabel(player.enrolled_date))}</span>
          ${placementMarkup(player)}
        </div>
        <div class="cam-batch-assignment-editor" aria-live="polite"></div>
      </div>`).join('');
  }

  function assignmentEditorMarkup(player, batches) {
    const activeBatches = batches.filter(batch => String(batch.status || '') === 'active');
    if (!activeBatches.length) {
      return `<div class="cam-batch-assignment-box"><strong>No active batches available.</strong><span>Create or activate a batch in Batches & Sessions first.</span><button type="button" class="secondary cam-batch-editor-cancel">Close</button></div>`;
    }

    const options = activeBatches.map(batch => {
      const activeCount = Number(batch.active_player_count || 0);
      const capacity = Number(batch.capacity || 0);
      const full = capacity > 0 && activeCount >= capacity;
      const program = batch.program_name ? ` · ${batch.program_name}` : '';
      const capacityLabel = capacity ? ` · ${activeCount}/${capacity}` : '';
      return `<option value="${esc(batch.id)}" ${full ? 'disabled' : ''}>${esc(batch.name || `Batch ${batch.id}`)}${esc(program)}${esc(capacityLabel)}${full ? ' · Full' : ''}</option>`;
    }).join('');
    const hasOpenBatch = activeBatches.some(batch => Number(batch.capacity || 0) <= 0 || Number(batch.active_player_count || 0) < Number(batch.capacity || 0));

    return `<form class="cam-batch-assignment-form" data-player-id="${esc(player.player_id)}">
      <div class="cam-batch-assignment-heading"><div><strong>Assign ${esc(player.player_name || 'player')} to a batch</strong><span>This creates the roster membership directly from the Dashboard.</span></div></div>
      <div class="cam-batch-assignment-fields">
        <label class="academy-field"><span>Batch *</span><select name="batch_id" required ${hasOpenBatch ? '' : 'disabled'}><option value="">Select batch</option>${options}</select></label>
        <label class="academy-field"><span>Start date *</span><input type="date" name="joined_on" value="${esc(player.enrolled_date || new Date().toISOString().slice(0, 10))}" required></label>
      </div>
      ${hasOpenBatch ? '' : '<p class="cam-batch-assignment-error">All active batches are currently full.</p>'}
      <div class="cam-batch-assignment-buttons">
        <span class="cam-batch-assignment-status"></span>
        <button type="button" class="secondary cam-batch-editor-cancel">Cancel</button>
        <button type="submit" class="primary" ${hasOpenBatch ? '' : 'disabled'}>Confirm Assignment</button>
      </div>
    </form>`;
  }

  function closeEditors(content) {
    $$('.cam-batch-assignment-editor', content).forEach(editor => { editor.innerHTML = ''; });
  }

  async function openAssignment(button, data, content) {
    const playerId = Number(button.dataset.playerId || 0);
    const player = (data?.players || []).find(item => Number(item.player_id) === playerId);
    const row = button.closest('.cam-new-enrollment-row');
    const editor = $('.cam-batch-assignment-editor', row);
    if (!player || !editor) return;

    closeEditors(content);
    editor.innerHTML = '<div class="cam-batch-assignment-box">Loading active batches…</div>';
    try {
      const batches = await loadBatches();
      editor.innerHTML = assignmentEditorMarkup(player, batches);
      const cancel = $('.cam-batch-editor-cancel', editor);
      if (cancel) cancel.onclick = () => { editor.innerHTML = ''; };
      const form = $('.cam-batch-assignment-form', editor);
      if (form) {
        form.onsubmit = async event => {
          event.preventDefault();
          const status = $('.cam-batch-assignment-status', form);
          const submit = $('button[type="submit"]', form);
          const values = new FormData(form);
          const batchId = Number(values.get('batch_id') || 0);
          const joinedOn = String(values.get('joined_on') || '').trim();
          if (!batchId) return;
          if (submit) submit.disabled = true;
          if (status) status.textContent = 'Assigning…';
          try {
            const membership = await requestJson(`/api/academy/batches/${batchId}/players`, {
              method:'POST',
              body:JSON.stringify({player_id:playerId, waitlist_if_full:false, joined_on:joinedOn}),
            });
            enrollmentCache = null;
            enrollmentCachedAt = 0;
            batchCache = null;
            batchCachedAt = 0;
            notify(`${player.player_name || 'Player'} assigned to ${membership?.batch_name || 'batch'}.`);
            render(await loadEnrollments());
          } catch (error) {
            if (status) status.textContent = error.message || 'Assignment failed.';
            if (submit) submit.disabled = false;
          }
        };
      }
    } catch (error) {
      editor.innerHTML = `<div class="cam-batch-assignment-box cam-batch-assignment-error">${esc(error.message || 'Could not load batches.')}<button type="button" class="secondary cam-batch-editor-cancel">Close</button></div>`;
      const cancel = $('.cam-batch-editor-cancel', editor);
      if (cancel) cancel.onclick = () => { editor.innerHTML = ''; };
    }
  }

  function wireAssignments(content, data) {
    $$('.cam-assign-batch', content).forEach(button => {
      button.onclick = () => openAssignment(button, data, content);
    });
  }

  function render(data) {
    if (!active()) return;
    const content = $('#academyWorkspace .academy-content');
    if (!content) return;

    let panel = existingRegistrationPanel(content) || $('.cam-new-player-enrollments', content);
    if (!panel) {
      const grid = $('.academy-dashboard-v2-grid', content) || $('.academy-dashboard-grid', content);
      if (!grid) return;
      panel = document.createElement('article');
      panel.className = 'panel academy-dash-panel cam-new-player-enrollments';
      grid.prepend(panel);
    } else {
      panel.classList.add('cam-new-player-enrollments');
    }

    const periodLabel = data?.period_label || '';
    const count = Number(data?.count || 0);
    const key = `${data?.period || ''}:${count}:${(data?.players || []).map(p => `${p.enrollment_id}:${p.enrolled_date}:${p.batch_id || ''}:${p.batch_status || ''}`).join('|')}`;
    if (panel.dataset.enrollmentKey === key) return;

    panel.innerHTML = `
      <div class="panel-head">
        <div>
          <h2>${esc(periodLabel)} - New Enrollment : ${count}</h2>
          <p>Players who successfully completed CAM enrollment this month.</p>
        </div>
      </div>
      <div class="cam-new-enrollment-list">${rowsMarkup(data?.players || [])}</div>`;
    panel.dataset.enrollmentKey = key;
    wireAssignments(content, data);
  }

  async function apply() {
    scheduled = false;
    if (!active() || loading) return;
    loading = true;
    try {
      render(await loadEnrollments());
    } catch (error) {
      console.warn('New player enrollment dashboard card unavailable:', error);
    } finally {
      loading = false;
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(apply);
  }

  window.addEventListener('hashchange', () => {
    enrollmentCache = null;
    enrollmentCachedAt = 0;
    schedule();
  });
  window.addEventListener('academy-enrollment-completed', () => {
    enrollmentCache = null;
    enrollmentCachedAt = 0;
    schedule();
  });
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(() => {
    if (active()) schedule();
  }).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
