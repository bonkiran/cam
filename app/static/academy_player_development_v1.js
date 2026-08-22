(() => {
  const MAX_SKILLS = 8;
  const wiredForms = new WeakSet();

  const esc = (value = '') => String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));

  async function api(url, options = {}) {
    const response = await fetch(url, {
      cache: 'no-store',
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
    });
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    return data;
  }

  function groupSkills(skills) {
    const groups = new Map();
    skills.forEach(skill => {
      const category = skill.category || 'Other';
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category).push(skill);
    });
    return groups;
  }

  function panelHtml(skills, focus) {
    const selected = new Set(focus.skill_keys || []);
    const groups = groupSkills(skills);
    const groupHtml = [...groups.entries()].map(([category, items]) => `
      <div class="cam-development-skill-group">
        <strong>${esc(category)}</strong>
        <div class="cam-development-skill-chips">
          ${items.map(skill => `
            <button
              type="button"
              class="cam-development-skill-chip ${selected.has(skill.skill_key) ? 'selected' : ''}"
              data-development-skill="${esc(skill.skill_key)}"
              aria-pressed="${selected.has(skill.skill_key) ? 'true' : 'false'}"
            >${esc(skill.name)}</button>
          `).join('')}
        </div>
      </div>
    `).join('');

    return `
      <section class="cam-development-focus" data-claim-level="training-exposure-only">
        <div class="cam-development-focus-head">
          <div>
            <span class="cam-kicker">MOAT · PLAYER DEVELOPMENT</span>
            <h3>Today's Development Focus</h3>
            <p>Select the skills this session is training once for the whole group. CAM applies them only to players marked <strong>Present</strong> or <strong>Late</strong>.</p>
          </div>
          <div class="cam-development-focus-count"><strong data-selected-count>${selected.size}</strong><span>/ ${MAX_SKILLS} selected</span></div>
        </div>
        <div class="cam-development-skill-groups">${groupHtml}</div>
        <div class="cam-development-focus-actions">
          <small><strong>Evidence rule:</strong> this records <em>Practiced / Exposed</em>. It does not claim the player improved.</small>
          <div>
            <span class="cam-development-focus-status" aria-live="polite"></span>
            <button type="button" class="secondary" data-clear-development-focus>Clear</button>
            <button type="button" class="primary" data-save-development-focus>Save Training Focus</button>
          </div>
        </div>
      </section>
    `;
  }

  function selectedKeys(panel) {
    return [...panel.querySelectorAll('[data-development-skill][aria-pressed="true"]')]
      .map(button => button.dataset.developmentSkill);
  }

  function updateSelectionState(panel) {
    const count = selectedKeys(panel).length;
    const countNode = panel.querySelector('[data-selected-count]');
    if (countNode) countNode.textContent = String(count);
    const save = panel.querySelector('[data-save-development-focus]');
    if (save) save.disabled = count > MAX_SKILLS;
  }

  async function wireForm(form) {
    if (!form || wiredForms.has(form)) return;
    wiredForms.add(form);

    const sessionId = Number(form.dataset.sessionId || 0);
    const roster = form.querySelector('.cam-attendance-roster');
    if (!sessionId || !roster) return;

    const loading = document.createElement('section');
    loading.className = 'cam-development-focus cam-development-loading';
    loading.innerHTML = '<strong>Loading development focus…</strong>';
    roster.before(loading);

    try {
      const [skills, focus] = await Promise.all([
        api('/api/cam/development/skills'),
        api(`/api/cam/sessions/${sessionId}/development-focus`)
      ]);
      loading.outerHTML = panelHtml(skills, focus);
      const panel = form.querySelector('.cam-development-focus');
      if (!panel) return;

      panel.querySelectorAll('[data-development-skill]').forEach(button => {
        button.addEventListener('click', () => {
          const pressed = button.getAttribute('aria-pressed') === 'true';
          if (!pressed && selectedKeys(panel).length >= MAX_SKILLS) {
            const status = panel.querySelector('.cam-development-focus-status');
            if (status) status.textContent = `Choose up to ${MAX_SKILLS} skills.`;
            return;
          }
          button.setAttribute('aria-pressed', pressed ? 'false' : 'true');
          button.classList.toggle('selected', !pressed);
          const status = panel.querySelector('.cam-development-focus-status');
          if (status) status.textContent = '';
          updateSelectionState(panel);
        });
      });

      panel.querySelector('[data-clear-development-focus]')?.addEventListener('click', () => {
        panel.querySelectorAll('[data-development-skill]').forEach(button => {
          button.setAttribute('aria-pressed', 'false');
          button.classList.remove('selected');
        });
        updateSelectionState(panel);
      });

      panel.querySelector('[data-save-development-focus]')?.addEventListener('click', async event => {
        const button = event.currentTarget;
        const status = panel.querySelector('.cam-development-focus-status');
        const keys = selectedKeys(panel);
        button.disabled = true;
        if (status) status.textContent = 'Saving…';
        try {
          const saved = await api(`/api/cam/sessions/${sessionId}/development-focus`, {
            method: 'PUT',
            body: JSON.stringify({ skill_keys: keys })
          });
          if (status) {
            const evidenceCount = Number(saved.generated_evidence_count || 0);
            status.textContent = evidenceCount
              ? `Saved · ${evidenceCount} practice evidence records linked.`
              : 'Saved · evidence will link automatically when attendance is recorded.';
          }
          if (typeof window.toast === 'function') window.toast('Training focus saved.');
        } catch (error) {
          if (status) status.textContent = error.message;
        } finally {
          button.disabled = false;
        }
      });

      updateSelectionState(panel);
    } catch (error) {
      loading.classList.add('cam-development-error');
      loading.innerHTML = `<strong>Development focus unavailable</strong><small>${esc(error.message)}</small>`;
    }
  }

  function scan() {
    document.querySelectorAll('#camAttendanceForm').forEach(form => wireForm(form));
  }

  const observer = new MutationObserver(scan);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('hashchange', scan);
  scan();
})();
