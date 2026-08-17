(() => {
  const CHILD_ROUTES = ['upload', 'analyses', 'comparisons'];
  let applying = false;

  function currentPage(){
    return (location.hash.replace(/^#/, '').split('?')[0] || 'dashboard');
  }

  function desiredOpen(page){
    return CHILD_ROUTES.includes(page) || localStorage.getItem('crick-analysis-menu-open') === '1';
  }

  function ensureAnalysisMenu(){
    if(applying) return;
    applying = true;
    try{
      const nav = document.querySelector('.sidebar .nav');
      if(!nav) return;

      let group = nav.querySelector('.analysis-nav-group');
      const directUpload = nav.querySelector(':scope > button[data-route="upload"]');

      if(!group){
        group = document.createElement('div');
        group.className = 'analysis-nav-group';
        group.innerHTML = `
          <button type="button" class="analysis-nav-parent" data-analysis-parent="1" aria-expanded="false">
            <i>◈</i><b>Analysis</b><span class="analysis-nav-caret">⌄</span>
          </button>
          <div class="analysis-nav-submenu"></div>`;
        if(directUpload) nav.insertBefore(group, directUpload);
        else nav.appendChild(group);
      }

      const submenu = group.querySelector('.analysis-nav-submenu');
      const parent = group.querySelector('[data-analysis-parent]');
      if(!submenu || !parent) return;

      CHILD_ROUTES.forEach(route => {
        let button = submenu.querySelector(`button[data-route="${route}"]`);
        if(!button){
          button = nav.querySelector(`:scope > button[data-route="${route}"]`);
          if(button) submenu.appendChild(button);
        }
        if(button){
          button.classList.add('analysis-nav-child');
          button.classList.toggle('active', currentPage() === route);
        }
      });

      const page = currentPage();
      const active = CHILD_ROUTES.includes(page);
      const open = desiredOpen(page);
      group.classList.toggle('active', active);
      group.classList.toggle('open', open);
      parent.classList.toggle('active', active);
      parent.setAttribute('aria-expanded', open ? 'true' : 'false');

      parent.onclick = () => {
        const nextOpen = !group.classList.contains('open');
        group.classList.toggle('open', nextOpen);
        parent.setAttribute('aria-expanded', nextOpen ? 'true' : 'false');
        localStorage.setItem('crick-analysis-menu-open', nextOpen ? '1' : '0');
      };
    } finally {
      applying = false;
    }
  }

  const observer = new MutationObserver(() => ensureAnalysisMenu());
  observer.observe(document.documentElement, {childList:true, subtree:true});
  window.addEventListener('hashchange', () => setTimeout(ensureAnalysisMenu, 0));
  document.addEventListener('DOMContentLoaded', ensureAnalysisMenu);
  ensureAnalysisMenu();
})();
