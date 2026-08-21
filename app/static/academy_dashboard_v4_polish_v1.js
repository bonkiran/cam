(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  let scheduled = false;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    return {page: page || 'dashboard', tab: new URLSearchParams(query).get('tab') || 'overview'};
  }

  const academyMode = () => route().page === 'academy';
  const dashboardActive = () => {
    const r = route();
    return r.page === 'academy' && r.tab === 'overview';
  };

  const ICONS = {
    home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10.5V20h14v-9.5"/><path d="M9 20v-6h6v6"/>',
    academy: '<path d="M3 21h18"/><path d="M5 21V4h14v17"/><path d="M8 7h2v2H8z"/><path d="M14 7h2v2h-2z"/><path d="M8 12h2v2H8z"/><path d="M14 12h2v2h-2z"/><path d="M10 21v-4h4v4"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/>',
    user: '<path d="M20 21a8 8 0 0 0-16 0"/><circle cx="12" cy="7" r="4"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    userPlus: '<path d="M15 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8" cy="7" r="4"/><path d="M19 8v6"/><path d="M22 11h-6"/>',
    clipboard: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4.5V3h6v1.5"/><path d="M9 9h6"/><path d="M9 13h6"/>',
    coaches: '<path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M21 8v6"/><path d="M18 11h6"/>',
    dollar: '<circle cx="12" cy="12" r="9"/><path d="M16 8.5c-.8-.9-2-1.5-3.5-1.5-2 0-3.5 1-3.5 2.5 0 3.5 7 1.5 7 5 0 1.5-1.5 2.5-3.5 2.5-1.6 0-3-.6-4-1.7"/><path d="M12 5v14"/>',
    chart: '<path d="M4 19V9"/><path d="M9 19V5"/><path d="M14 19v-7"/><path d="M19 19V3"/><path d="M3 21h18"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.1A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.1A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.1A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.2.36.5.72.9 1 .32.2.7.35 1.1.4h.1v4h-.1c-.4.05-.78.2-1.1.4-.4.28-.7.64-.9 1.2Z"/>',
    activity: '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.8 9a2.4 2.4 0 1 1 3.8 2c-.9.6-1.6 1.1-1.6 2.3"/><path d="M12 17h.01"/>',
    list: '<path d="M9 6h11"/><path d="M9 12h11"/><path d="M9 18h11"/><path d="m4 6 1 1 2-2"/><path d="m4 12 1 1 2-2"/><path d="m4 18 1 1 2-2"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4"/><path d="M8 3v4"/><path d="M3 10h18"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/>',
    calendarRange: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4"/><path d="M8 3v4"/><path d="M3 10h18"/><path d="M7 15h4"/><path d="M13 15h4"/>',
    wallet: '<path d="M4 7h14a2 2 0 0 1 2 2v10H4a2 2 0 0 1-2-2V7a3 3 0 0 1 3-3h12"/><path d="M16 12h6v4h-6a2 2 0 0 1 0-4Z"/>',
  };

  function svg(name, className = '') {
    const body = ICONS[name] || ICONS.user;
    return `<svg class="c17-svg ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  }

  const sidebarIcons = {
    Dashboard:'home', Academy:'academy', Registration:'edit', Players:'user', Programs:'clipboard',
    Coaches:'coaches', Finance:'dollar', Reports:'chart', Settings:'settings', Insights:'activity', 'Help & Support':'help'
  };

  function polishSidebar() {
    if (!academyMode()) return;
    $$('.c17-nav-item').forEach(button => {
      const label = $('b', button)?.textContent.trim() || '';
      const holder = $('i', button);
      const key = sidebarIcons[label] || 'user';
      if (!holder || holder.dataset.prototypeIcon === key) return;
      holder.innerHTML = svg(key, 'c17-nav-svg');
      holder.dataset.prototypeIcon = key;
    });
  }

  function titleIconFor(text) {
    if (text.includes('Players in Programs')) return 'users';
    if (text.includes('New Enrollment')) return 'userPlus';
    if (text.includes('Enrollment Tracker')) return 'list';
    if (text.includes('Sessions')) return 'calendar';
    if (text.includes('Upcoming Events')) return 'calendarRange';
    if (text.includes('Session Attendance')) return 'users';
    if (text.includes('Academy Receipts')) return 'dollar';
    if (text.includes('Academy Payments')) return 'wallet';
    return null;
  }

  function polishCardIcons(root) {
    $$('.c17-card-title', root).forEach(title => {
      const text = $('h2', title)?.textContent || '';
      const key = titleIconFor(text);
      const icon = $('.c17-icon', title);
      if (!key || !icon || icon.dataset.prototypeIcon === key) return;
      icon.innerHTML = svg(key, 'c17-title-svg');
      icon.dataset.prototypeIcon = key;
    });

    $$('.c17-program', root).forEach(card => {
      const strong = $('strong', card);
      if (!strong || $('.c17-program-person', strong)) return;
      strong.insertAdjacentHTML('beforeend', svg('user', 'c17-program-person'));
    });
  }

  function monthLabelFromDashboard(root) {
    const newEnrollment = $$('.c17-card-title h2', root).find(h => h.textContent.includes('New Enrollment'));
    const match = newEnrollment?.textContent.match(/^(.+?)\s*-\s*New Enrollment/i);
    if (match?.[1]) return match[1].trim();
    return new Date().toLocaleDateString(undefined, {month:'long', year:'numeric'});
  }

  function polishEnrollmentTracker(root) {
    const grid = $('.c17-enrollment-grid', root);
    if (!grid) return;
    $('.c17-links-card', grid)?.remove();
    grid.classList.add('c17-tracker-full');

    const tracker = $('.c17-tracker-card', grid) || $('.c17-card', grid);
    const heading = $('h2', tracker);
    if (!heading) return;
    const count = heading.textContent.match(/Tracker\s*:\s*(\d+)/i)?.[1] || '0';
    const next = `${monthLabelFromDashboard(root)} - Enrollment Tracker : ${count}`;
    if (heading.textContent !== next) heading.textContent = next;
  }

  function polishFinance(root) {
    let row = $('.c17-finance-row', root);
    if (row) return;
    const cards = $$(':scope > .c17-card', root);
    const receipts = cards.find(card => $('h2', card)?.textContent.includes('Academy Receipts'));
    const payments = cards.find(card => $('h2', card)?.textContent.includes('Academy Payments'));
    if (!receipts || !payments) return;
    row = document.createElement('section');
    row.className = 'c17-finance-row';
    receipts.before(row);
    row.append(receipts, payments);
  }

  function hideTopAcademyNav() {
    if (!academyMode()) return;
    $$('#academyWorkspace > .academy-primary-nav, #academyWorkspace > .academy-tabs').forEach(nav => {
      nav.setAttribute('aria-hidden', 'true');
      nav.style.display = 'none';
    });
  }

  function apply() {
    scheduled = false;
    if (!academyMode()) return;
    hideTopAcademyNav();
    polishSidebar();
    if (!dashboardActive()) return;
    const root = $('.c17-dashboard');
    if (!root) return;
    polishEnrollmentTracker(root);
    polishFinance(root);
    polishCardIcons(root);
    root.dataset.prototypePolish = '1';
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(apply);
  }

  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(() => { if (academyMode()) schedule(); }).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
