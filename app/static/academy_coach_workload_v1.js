(() => {
  let scheduled = false;
  let running = false;
  let lastSignature = '';

  function tabFromHash() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    if (page !== 'academy') return null;
    return new URLSearchParams(query).get('tab') || 'overview';
  }

  async function json(url) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    return response.json();
  }

  function formatHours(minutes) {
    const hours = Number(minutes || 0) / 60;
    if (Number.isInteger(hours)) return `${hours}h`;
    return `${hours.toFixed(1)}h`;
  }

  async function applyWorkload() {
    if (running || tabFromHash() !== 'coaches') return;
    const rows = [...document.querySelectorAll('.academy-coach-row[data-coach-row]')];
    if (!rows.length) return;

    const signature = rows.map(row => row.dataset.coachRow).join(',');
    if (signature === lastSignature && rows.every(row => row.dataset.workloadApplied === '1')) return;

    running = true;
    try {
      const workloads = await Promise.all(rows.map(async row => {
        const coachId = Number(row.dataset.coachRow);
        const data = await json(`/api/academy/coaches/${coachId}/workload`);
        return { row, data };
      }));

      let totalSessions = 0;
      let totalMinutes = 0;
      workloads.forEach(({ row, data }) => {
        totalSessions += Number(data.session_count || 0);
        totalMinutes += Number(data.total_minutes || 0);
        const tags = row.querySelector('.academy-program-tags');
        if (tags) {
          let tag = tags.querySelector('[data-coach-workload]');
          if (!tag) {
            tag = document.createElement('span');
            tag.dataset.coachWorkload = '1';
            tags.appendChild(tag);
          }
          const sessions = Number(data.session_count || 0);
          tag.textContent = `${sessions} session${sessions === 1 ? '' : 's'} · ${formatHours(data.total_minutes)}`;
        }
        row.dataset.workloadApplied = '1';
      });

      const stat = [...document.querySelectorAll('.academy-stat')].find(card =>
        card.querySelector('span')?.textContent?.trim() === 'Session workload'
      );
      if (stat) {
        const strong = stat.querySelector('strong');
        const small = stat.querySelector('small');
        if (strong) strong.textContent = String(totalSessions);
        if (small) small.textContent = `${formatHours(totalMinutes)} scheduled coaching time`;
      }
      lastSignature = signature;
    } catch (error) {
      console.warn('Coach workload could not be loaded', error);
    } finally {
      running = false;
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      applyWorkload();
    }, 60);
  }

  window.addEventListener('hashchange', () => {
    lastSignature = '';
    schedule();
  });
  new MutationObserver(() => {
    if (tabFromHash() === 'coaches') schedule();
  }).observe(document.documentElement, { childList: true, subtree: true });
  schedule();
})();
