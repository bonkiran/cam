(() => {
  function setActiveOwnerTab(button) {
    const tabs = button.closest('#academyWorkspace .academy-tabs');
    if (!tabs) return;
    tabs.querySelectorAll('[data-owner-console-tab]').forEach((tab) => {
      const active = tab === button;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-current', active ? 'page' : 'false');
    });
  }

  // Owner/Admin tabs are injected after the base academy navigation handlers are wired.
  // Apply pressed-tab feedback during the click event itself so the first painted frame
  // reflects the user's selection; the route renderer subsequently confirms the state.
  document.addEventListener('click', (event) => {
    const button = event.target.closest?.('#academyWorkspace .academy-tabs [data-owner-console-tab]');
    if (!button || button.hidden || button.disabled) return;
    setActiveOwnerTab(button);
  }, true);
})();
