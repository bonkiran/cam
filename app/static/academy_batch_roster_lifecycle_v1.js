(() => {
  let enhancing = false;
  let scheduled = false;

  function currentTab() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    if (page !== 'academy') return null;
    return new URLSearchParams(query).get('tab') || 'overview';
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      cache: 'no-store',
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    return data;
  }

  function notify(message) {
    if (typeof window.toast === 'function') window.toast(message);
    else console.log(message);
  }

  async function membershipsInDisplayOrder() {
    const batches = await requestJson('/api/academy/batches');
    const groups = await Promise.all(
      batches.map(async batch => {
        const memberships = await requestJson(`/api/academy/batches/${batch.id}/players`);
        return memberships.map(membership => ({ ...membership, batch_name: batch.name }));
      }),
    );
    return groups.flat();
  }

  async function perform(button, url, successMessage) {
    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = 'Working…';
    try {
      await requestJson(url, { method: 'POST', body: JSON.stringify({}) });
      notify(successMessage);
      // The base Batches workspace keeps its renderer private. A reload is a
      // deliberate rare-action refresh so batch counts, roster and generated
      // session player counts all reflect the same committed lifecycle change.
      location.reload();
    } catch (error) {
      notify(error.message);
      button.disabled = false;
      button.textContent = oldText;
    }
  }

  async function enhanceRoster() {
    if (enhancing || currentTab() !== 'batches') return;
    const container = document.querySelector('#academyWorkspace .academy-batch-membership-list');
    if (!container || container.dataset.rosterLifecycleEnhanced === '1') return;

    const rows = [...container.querySelectorAll('.academy-batch-membership-row')];
    if (!rows.length) return;

    enhancing = true;
    try {
      const memberships = await membershipsInDisplayOrder();
      if (memberships.length !== rows.length) return;

      rows.forEach((row, index) => {
        const membership = memberships[index];
        row.dataset.membershipId = String(membership.id);
        row.dataset.batchId = String(membership.batch_id);

        if (!['active', 'waitlisted'].includes(String(membership.status))) return;

        const actions = document.createElement('div');
        actions.className = 'academy-program-actions academy-roster-lifecycle-actions';
        actions.style.display = 'flex';
        actions.style.gap = '6px';
        actions.style.alignItems = 'center';

        if (membership.status === 'waitlisted') {
          const promote = document.createElement('button');
          promote.type = 'button';
          promote.textContent = 'Promote';
          promote.title = 'Promote this player when batch capacity is available';
          promote.addEventListener('click', () => perform(
            promote,
            `/api/academy/batches/${membership.batch_id}/players/${membership.id}/promote`,
            `${membership.player_name} promoted to the active roster.`,
          ));
          actions.appendChild(promote);
        }

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'danger';
        remove.textContent = membership.status === 'waitlisted' ? 'Remove' : 'Remove';
        remove.title = membership.status === 'waitlisted' ? 'Remove this player from the waitlist' : 'End this active batch membership';
        remove.addEventListener('click', () => perform(
          remove,
          `/api/academy/batches/${membership.batch_id}/players/${membership.id}/end`,
          `${membership.player_name} removed from the current batch roster.`,
        ));
        actions.appendChild(remove);
        row.appendChild(actions);
      });

      container.dataset.rosterLifecycleEnhanced = '1';
    } catch (error) {
      console.warn('Batch roster lifecycle controls unavailable', error);
    } finally {
      enhancing = false;
    }
  }

  function scheduleEnhance() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      enhanceRoster();
    }, 50);
  }

  const observer = new MutationObserver(scheduleEnhance);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('hashchange', scheduleEnhance);
  document.addEventListener('DOMContentLoaded', scheduleEnhance);
  scheduleEnhance();
})();
