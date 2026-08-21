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
    return r.page === 'academy' && r.tab === 'programs';
  }

  function hideLegacyProgramTabs() {
    document.querySelectorAll('.academy-tabs, .academy-primary-nav').forEach(node => {
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
    button.addEventListener('click', () => goToCreateAction(action, hash));
    return button;
  }

  async function enhanceProgramsPage() {
    if (enhancing || !isProgramsPage()) return;
    const content = $('#academyWorkspace .academy-content');
    if (!content || content.dataset.c17ProgramsHub === '1') return;
    const legacyHeader = $('.academy-section-head', content);
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
      actions.appendChild(buildButton('Create Batches', 'create-batch', 'academy?tab=batches'));
      actions.appendChild(buildButton('Create Sessions', 'create-sessions', 'academy?tab=batches'));
      actions.appendChild(buildButton('Create Matches', 'create-match', 'academy?tab=teams'));
      actions.appendChild(buildButton('Create Tournaments', 'create-tournament', 'academy?tab=tournaments'));

      hero.insertAdjacentElement('afterend', toolbar);
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
      'create-sessions': {tab:'batches', selector:'#openBatchSchedule'},
      'create-match': {tab:'teams', selector:'#openFixtureForm'},
      'create-tournament': {tab:'tournaments', selector:'#openTournamentForm'}
    };
    const target = map[action];
    if (!target || r.page !== 'academy' || r.tab !== target.tab) return;

    const button = $(target.selector, $('#academyWorkspace .academy-content') || document);
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
