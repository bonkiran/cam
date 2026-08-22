(() => {
  const priorFetch = window.fetch.bind(window);

  function tournamentWrite(input, init = {}) {
    try {
      const url = new URL(typeof input === 'string' ? input : input.url, location.origin);
      const method = String(init.method || 'GET').toUpperCase();
      return /^\/api\/academy\/tournaments(?:\/\d+)?$/.test(url.pathname) && (method === 'POST' || method === 'PUT');
    } catch (_) {
      return false;
    }
  }

  // cam_tournaments_v1.js predates the explicit internal/external field and
  // builds a fixed JSON payload from its form. Keep that stable module intact and
  // enrich only tournament writes with the selected classification.
  window.fetch = (input, init = {}) => {
    if (tournamentWrite(input, init) && typeof init.body === 'string') {
      try {
        const payload = JSON.parse(init.body);
        if (!payload.tournament_type) {
          payload.tournament_type = document.querySelector('#camTournamentForm [name="tournament_type"]')?.value || 'external';
          init = { ...init, body: JSON.stringify(payload) };
        }
      } catch (_) {}
    }
    return priorFetch(input, init);
  };

  async function loadCurrentType(form, select) {
    const id = Number(form.dataset.tournamentId || 0);
    if (!id) return;
    try {
      const response = await priorFetch(`/api/cam/tournaments/${id}`, { cache: 'no-store' });
      if (!response.ok) return;
      const tournament = await response.json();
      select.value = tournament.tournament_type || 'external';
    } catch (_) {}
  }

  function enhanceForm() {
    const form = document.querySelector('#camTournamentForm');
    if (!form || form.dataset.tournamentTypeEnhanced === '1') return;
    const grid = form.querySelector('.cam-form-grid');
    if (!grid) return;

    const label = document.createElement('label');
    label.className = 'cam-field';
    label.innerHTML = `
      <span>Tournament Type *</span>
      <select name="tournament_type" required>
        <option value="external">External</option>
        <option value="internal">Internal</option>
      </select>`;

    const organizer = grid.querySelector('[name="organizer"]')?.closest('label');
    if (organizer) grid.insertBefore(label, organizer);
    else grid.prepend(label);

    const select = label.querySelector('select');
    form.dataset.tournamentTypeEnhanced = '1';
    loadCurrentType(form, select);
  }

  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      enhanceForm();
    }, 25);
  }

  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  schedule();
})();
