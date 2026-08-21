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

  async function requestJson(url) {
    const response = await fetch(url, {cache:'no-store'});
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

  async function rosterMap() {
    const groups = Object.fromEntries(GROUPS.map(name => [name, new Set()]));
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
        if (playerId) groups[group].add(playerId);
      });
    });
    return groups;
  }

  function batchPanel(name) {
    const panel = document.createElement('article');
    panel.className = 'panel c17-player-batch-panel';
    panel.dataset.playerBatch = name;
    panel.innerHTML = `<div class="c17-player-batch-head"><div><h3>${name}</h3><p>Players currently assigned to this batch.</p></div><strong class="c17-player-batch-count">0</strong></div><div class="c17-player-batch-list"></div>`;
    return panel;
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
      const [heroMarkup, groups] = await Promise.all([
        window.C17AcademyHeader?.hero
          ? window.C17AcademyHeader.hero({title:'Players', subtitle:'C17 Academy Players'})
          : Promise.resolve('<section class="c17-hero c17-page-hero"><div class="c17-welcome"><h1>Players</h1><p>C17 Academy Players</p></div></section>'),
        rosterMap()
      ]);

      if (!active() || !content.isConnected) return;

      const rowById = new Map(legacyRows.map(row => [Number(row.dataset.playerId || 0), row]));
      const assigned = new Set();
      const page = document.createElement('section');
      page.className = 'c17-players-page';
      page.innerHTML = `${heroMarkup}<div class="c17-player-editor-host"></div><section class="c17-player-records"><div class="c17-player-records-head"><div><h2>Player Records</h2><p class="c17-player-records-summary"></p></div><div class="c17-player-add-host"></div></div><div class="c17-player-batch-grid"></div></section>`;

      if (editor) $('.c17-player-editor-host', page).appendChild(editor);
      if (addButton) $('.c17-player-add-host', page).appendChild(addButton);

      const grid = $('.c17-player-batch-grid', page);
      GROUPS.forEach(name => {
        const panel = batchPanel(name);
        const list = $('.c17-player-batch-list', panel);
        const ids = [...groups[name]].filter(id => rowById.has(id));
        ids.sort((a, b) => {
          const an = $('strong', rowById.get(a))?.textContent || '';
          const bn = $('strong', rowById.get(b))?.textContent || '';
          return an.localeCompare(bn);
        });
        ids.forEach(id => {
          assigned.add(id);
          list.appendChild(rowById.get(id));
        });
        $('.c17-player-batch-count', panel).textContent = String(ids.length);
        if (!ids.length) list.innerHTML = '<div class="c17-player-batch-empty">No players assigned.</div>';
        grid.appendChild(panel);
      });

      const summary = $('.c17-player-records-summary', page);
      if (summary) summary.textContent = `${assigned.size} player${assigned.size === 1 ? '' : 's'} assigned across Beginners, U11, U13, U14 and U15.`;

      content.replaceChildren(page);
      content.dataset.c17PlayersRendered = '1';
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
