(() => {
  const labels = {
    dashboard: 'Cricket performance workspace',
    upload: 'Video ingest & coaching review',
    analyses: 'Analysis library',
    players: 'Player intelligence',
    comparisons: 'Player & shot comparison',
    'shot-library': 'Shot evidence library',
    reports: 'Coaching reports',
    insights: 'Cricket insights',
    sessions: 'Training sessions',
    settings: 'Workspace settings',
    integrations: 'Cricket tool ecosystem',
    help: 'CrickAnalysis support',
    analysis: 'Frame-by-frame coaching review'
  };

  const photoPage = 'https://unsplash.com/photos/a-wide-view-of-a-cricket-stadium-with-green-field-bbrEFf5UlCE';

  function currentPage() {
    return (location.hash.replace(/^#/, '').split('?')[0] || 'dashboard');
  }

  function enhanceTheme() {
    const page = currentPage();
    document.body.dataset.crickPage = page;

    const head = document.querySelector('.page-head');
    if (!head) return;
    const copy = head.querySelector(':scope > div:first-child');
    if (copy && !copy.querySelector('.page-kicker')) {
      const kicker = document.createElement('div');
      kicker.className = 'page-kicker';
      kicker.textContent = labels[page] || 'Cricket analysis workspace';
      copy.insertBefore(kicker, copy.firstChild);
    }

    if (!head.querySelector('.ground-credit')) {
      const credit = document.createElement('a');
      credit.className = 'ground-credit';
      credit.href = photoPage;
      credit.target = '_blank';
      credit.rel = 'noopener noreferrer';
      credit.textContent = 'Real ground photo · Zoshua Colah / Unsplash';
      head.appendChild(credit);
    }
  }

  let timer;
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(enhanceTheme, 20);
  }

  window.addEventListener('hashchange', schedule);
  window.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  schedule();
})();
