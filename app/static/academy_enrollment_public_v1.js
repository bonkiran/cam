(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const token = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop() || '');

  function esc(v = '') {
    return String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  function academyLabel(name) {
    const clean = String(name || 'Academy').trim() || 'Academy';
    return /academy$/i.test(clean) ? clean : `${clean} Academy`;
  }

  function statusLabel(status) {
    const map = {created:'Link Created',sent:'Sent',opened:'Opened',in_progress:'In Progress',completed:'Complete'};
    return map[status] || status || '—';
  }

  async function request(url, options = {}) {
    const res = await fetch(url, {
      cache: 'no-store',
      ...options,
      headers: {'Content-Type':'application/json', ...(options.headers || {})},
    });
    let data = null;
    try { data = await res.json(); } catch {}
    if (!res.ok) throw new Error(data?.detail || `Request failed (${res.status})`);
    return data;
  }

  function renderSteps(steps = [], currentStatus = '') {
    const host = $('#enrollmentSteps');
    if (!host) return;
    host.innerHTML = steps.map((step, index) => {
      let state = 'later';
      if (index === 0) state = currentStatus === 'in_progress' ? 'done' : 'current';
      if (index === 1 && currentStatus === 'in_progress') state = 'current';
      const marker = state === 'done' ? '✓' : String(index + 1);
      return `<div class="step ${state}"><span>${marker}</span><div><strong>${esc(step.label)}</strong><small>${state === 'done' ? 'Completed' : state === 'current' ? 'Current step' : 'Upcoming'}</small></div></div>`;
    }).join('');
  }

  async function load() {
    if (!token) return showError('The enrollment link is incomplete.');
    try {
      const data = await request(`/api/public/enrollment/${encodeURIComponent(token)}`);
      const enrollment = data?.enrollment || {};
      const academy = academyLabel(enrollment.academy_name);
      document.title = `${academy} Parent Enrollment`;
      $('#enrollmentTitle').textContent = `${academy} Parent Enrollment`;
      $('#enrollmentSubtitle').textContent = `Complete the remaining enrollment steps for ${enrollment.player_name || 'your player'}.`;
      $('#enrollmentPlayer').textContent = enrollment.player_name || '—';
      $('#enrollmentParent').textContent = [enrollment.parent_first_name, enrollment.parent_last_name].filter(Boolean).join(' ') || '—';
      $('#enrollmentStatus').textContent = statusLabel(enrollment.status);
      renderSteps(data?.steps || [], enrollment.status);
      $('#enrollmentLoading').hidden = true;
      $('#enrollmentPortal').hidden = false;
      if (enrollment.status === 'in_progress') {
        $('#welcomeCard').hidden = true;
        $('#nextCard').hidden = false;
      }
    } catch (err) {
      showError(err.message);
    }
  }

  function showError(message) {
    $('#enrollmentLoading').hidden = true;
    $('#enrollmentPortal').hidden = true;
    $('#enrollmentError').hidden = false;
    $('#enrollmentErrorText').textContent = message;
  }

  $('#startEnrollment')?.addEventListener('click', async e => {
    const button = e.currentTarget;
    button.disabled = true;
    button.textContent = 'Starting…';
    try {
      await request(`/api/public/enrollment/${encodeURIComponent(token)}/start`, {method:'POST', body:'{}'});
      $('#enrollmentStatus').textContent = 'In Progress';
      renderSteps([
        {label:'Enrollment Summary'},
        {label:'Agreements & Documents'},
        {label:'Fees & Payment'},
        {label:'Complete'},
      ], 'in_progress');
      $('#welcomeCard').hidden = true;
      $('#nextCard').hidden = false;
      window.scrollTo({top:0, behavior:'smooth'});
    } catch (err) {
      button.disabled = false;
      button.textContent = 'Start Enrollment';
      alert(err.message);
    }
  });

  load();
})();
