(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const ACTION_KEY = 'c17ProgramCreateAction';
  let enhancing = false;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    return {
      page: page || 'dashboard',
      tab: new URLSearchParams(query).get('tab') || 'overview'
    };
  }

  function isProgramsPage() {
    const r = route();
    return r.page === 'cam' && r.tab === 'programs';
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

  function hideLegacyProgramTabs() {
    document.querySelectorAll('.cam-tabs, .cam-primary-nav').forEach(node => {
      node.style.display = 'none';
      node.setAttribute('aria-hidden', 'true');
    });
  }

  function goToCreateAction(action, hash) {
    try { sessionStorage.setItem(ACTION_KEY, action); } catch {}
    location.hash = hash;
  }

  function buildButton(label, action, hash) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'secondary';
    button.textContent = `＋ ${label}`;
    if (action === 'create-sessions') {
      button.addEventListener('click', openInlineSessions);
    } else {
      button.addEventListener('click', () => goToCreateAction(action, hash));
    }
    return button;
  }

  function scheduleForm(batches) {
    const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const options = batches.map(batch => `<option value="${Number(batch.id)}">${esc(batch.name || `Batch ${batch.id}`)}</option>`).join('');
    return `<form id="c17ProgramScheduleForm" class="panel cam-form-card">
      <div class="cam-form-title">
        <div><span class="cam-kicker">RECURRING SCHEDULE</span><h2>Generate Batch Sessions</h2><p>Dates/times are stored in the Academy timezone. Existing identical occurrences are not duplicated.</p></div>
        <button type="button" class="secondary" data-close-program-schedule>Cancel</button>
      </div>
      <div class="cam-form-grid three">
        <label class="cam-field"><span>Batch *</span><select name="batch_id" required><option value="">Select</option>${options}</select></label>
        <label class="cam-field"><span>Start Date *</span><input type="date" name="start_date" required></label>
        <label class="cam-field"><span>End Date *</span><input type="date" name="end_date" required></label>
        <label class="cam-field"><span>Start Time *</span><input type="time" name="start_time" value="19:00" required></label>
        <label class="cam-field"><span>Duration (minutes) *</span><input type="number" name="duration_minutes" value="60" required></label>
      </div>
      <div class="cam-weekdays"><span>Training days *</span>${days.map((day, index) => `<label><input type="checkbox" name="weekday" value="${index}"> ${day}</label>`).join('')}</div>
      <div class="cam-form-actions"><span id="c17ProgramScheduleStatus"></span><button type="submit" class="primary">Generate Sessions</button></div>
    </form>`;
  }

  async function openInlineSessions() {
    if (!isProgramsPage()) return;
    const content = $('#camWorkspace .cam-content');
    const host = $('#c17ProgramInlineAction', content || document);
    if (!content || !host) return;

    host.innerHTML = '<div class="panel cam-loading">Loading active batches…</div>';
    try {
      const batches = await requestJson('/api/cam/batches');
      if (!isProgramsPage() || !host.isConnected) return;
      const activeBatches = (Array.isArray(batches) ? batches : []).filter(batch => String(batch.status || 'active').toLowerCase() === 'active');
      if (!activeBatches.length) {
        host.innerHTML = '';
        notify('Create an active batch before generating sessions.');
        return;
      }

      host.innerHTML = scheduleForm(activeBatches);
      $('[data-close-program-schedule]', host)?.addEventListener('click', () => { host.innerHTML = ''; });
      const form = $('#c17ProgramScheduleForm', host);
      if (form) {
        form.addEventListener('submit', async event => {
          event.preventDefault();
          const status = $('#c17ProgramScheduleStatus', form);
          const submit = $('button[type="submit"]', form);
          const data = new FormData(form);
          const weekdays = data.getAll('weekday').map(Number);
          if (!weekdays.length) {
            if (status) status.textContent = 'Select at least one training day.';
            return;
          }

          if (submit) submit.disabled = true;
          if (status) status.textContent = 'Generating…';
          try {
            const batchId = Number(data.get('batch_id'));
            const result = await requestJson(`/api/cam/batches/${batchId}/generate-sessions`, {
              method:'POST',
              body:JSON.stringify({
                start_date:data.get('start_date'),
                end_date:data.get('end_date'),
                weekdays,
                start_time:data.get('start_time'),
                duration_minutes:Number(data.get('duration_minutes'))
              })
            });
            const count = Number(result?.created_count || 0);
            if (status) status.textContent = `${count} session${count === 1 ? '' : 's'} generated.`;
            notify(`${count} session${count === 1 ? '' : 's'} generated.`);
          } catch (error) {
            if (status) status.textContent = error.message;
          } finally {
            if (submit) submit.disabled = false;
          }
        });
      }
      host.scrollIntoView({behavior:'smooth', block:'start'});
    } catch (error) {
      host.innerHTML = `<div class="warning">${esc(error.message)}</div>`;
    }
  }

  async function enhanceProgramsPage() {
    if (enhancing || !isProgramsPage()) return;
    const content = $('#camWorkspace .cam-content');
    if (!content || content.dataset.c17ProgramsHub === '1') return;
    const legacyHeader = $('.cam-section-head', content);
    if (!legacyHeader) return;

    enhancing = true;
    try {
      const createProgramButton = $('#openProgramForm', legacyHeader) || $('#openProgramForm', content);
      $('#openEnrollmentForm', content)?.remove();

      const heroMarkup = window.C17AcademyHeader?.hero
        ? await window.C17AcademyHeader.hero({title:'Programs', subtitle:'C17 Academy Programs'})
        : '<section class="c17-hero c17-page-hero"><div class="c17-welcome"><h1>Programs</h1><p>C17 Academy Programs</p></div></section>';

      if (!isProgramsPage() || !content.isConnected) return;

      const heroHost = document.createElement('div');
      heroHost.innerHTML = heroMarkup;
      const hero = heroHost.firstElementChild;
      if (!hero) return;
      legacyHeader.replaceWith(hero);

      const toolbar = document.createElement('section');
      toolbar.className = 'panel c17-program-operations-panel';
      toolbar.innerHTML = '<div class="c17-program-operations-copy"><h2>Program Operations</h2><p>Create and manage the academy schedule, matches and tournaments from one place.</p></div><div class="c17-program-operations-actions"></div>';
      const actions = $('.c17-program-operations-actions', toolbar);

      if (createProgramButton) {
        createProgramButton.textContent = '＋ Create Program';
        createProgramButton.classList.remove('secondary');
        createProgramButton.classList.add('primary');
        actions.appendChild(createProgramButton);
      }
      actions.appendChild(buildButton('Create Batches', 'create-batch', 'cam?tab=batches'));
      actions.appendChild(buildButton('Create Sessions', 'create-sessions', 'cam?tab=batches'));
      actions.appendChild(buildButton('Create Matches', 'create-match', 'cam?tab=teams'));
      actions.appendChild(buildButton('Create Tournaments', 'create-tournament', 'cam?tab=tournaments'));

      hero.insertAdjacentElement('afterend', toolbar);

      const stats = $('.cam-stats', content);
      if (stats && !$('#c17ProgramInlineAction', content)) {
        const inlineHost = document.createElement('div');
        inlineHost.id = 'c17ProgramInlineAction';
        inlineHost.className = 'cam-program-editor c17-program-inline-action';
        stats.insertAdjacentElement('afterend', inlineHost);
      }

      content.dataset.c17ProgramsHub = '1';
    } catch (error) {
      console.error('Could not build C17 Programs header/actions', error);
    } finally {
      enhancing = false;
    }
  }

  function runPendingCreateAction() {
    let action = null;
    try { action = sessionStorage.getItem(ACTION_KEY); } catch {}
    if (!action) return;

    const r = route();
    const map = {
      'create-batch': {tab:'batches', selector:'#openBatchForm'},
      'create-match': {tab:'teams', selector:'#openFixtureForm'},
      'create-tournament': {tab:'tournaments', selector:'#openTournamentForm'}
    };
    const target = map[action];
    if (!target || r.page !== 'cam' || r.tab !== target.tab) return;

    const button = $(target.selector, $('#camWorkspace .cam-content') || document);
    if (!button) return;
    try { sessionStorage.removeItem(ACTION_KEY); } catch {}
    button.click();
  }

  function apply() {
    hideLegacyProgramTabs();
    if (isProgramsPage()) enhanceProgramsPage();
    runPendingCreateAction();
  }

  window.addEventListener('hashchange', () => setTimeout(apply, 0));
  new MutationObserver(() => queueMicrotask(apply)).observe(document.documentElement, {childList:true, subtree:true});
  setTimeout(apply, 0);
})();
