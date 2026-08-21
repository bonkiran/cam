(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  let scheduled = false;
  let loading = false;
  let cached = null;
  let cachedAt = 0;

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
    return String(value ?? '').replace(/[&<>'\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));
  }

  function dateLabel(value) {
    if (!value) return '—';
    const date = new Date(`${String(value).slice(0, 10)}T12:00:00`);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'});
  }

  async function load() {
    const now = Date.now();
    if (cached && now - cachedAt < 15000) return cached;
    const response = await fetch('/api/academy/dashboard/new-player-enrollments', {cache:'no-store'});
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    cached = data || {count:0, players:[]};
    cachedAt = now;
    return cached;
  }

  function existingRegistrationPanel(content) {
    const title = $$('h1,h2,h3,h4,strong,b,span,div', content).find(node => {
      if (node.children.length) return false;
      const text = (node.textContent || '').trim();
      return text === 'New Player Registrations' || text.startsWith('New Player Registrations:');
    });
    return title?.closest('article,.panel,section') || null;
  }

  function rowsMarkup(players = []) {
    if (!players.length) {
      return '<div class="academy-dash-empty">No players have completed enrollment this month.</div>';
    }
    return players.map(player => `
      <div class="academy-dash-session cam-new-enrollment-row">
        <div>
          <strong>${esc(player.player_name || 'Player')}</strong>
          <small>Enrollment complete</small>
        </div>
        <span>Enrolled ${esc(dateLabel(player.enrolled_date))}</span>
      </div>`).join('');
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
    const key = `${data?.period || ''}:${count}:${(data?.players || []).map(p => `${p.enrollment_id}:${p.enrolled_date}`).join('|')}`;
    if (panel.dataset.enrollmentKey === key) return;

    panel.innerHTML = `
      <div class="panel-head">
        <div>
          <h2>New Player Enrolled: ${count} (${esc(periodLabel)})</h2>
          <p>Players who successfully completed CAM enrollment this month.</p>
        </div>
      </div>
      <div class="cam-new-enrollment-list">${rowsMarkup(data?.players || [])}</div>`;
    panel.dataset.enrollmentKey = key;
  }

  async function apply() {
    scheduled = false;
    if (!active() || loading) return;
    loading = true;
    try {
      render(await load());
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
    cached = null;
    cachedAt = 0;
    schedule();
  });
  window.addEventListener('academy-enrollment-completed', () => {
    cached = null;
    cachedAt = 0;
    schedule();
  });
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(() => {
    if (active()) schedule();
  }).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
