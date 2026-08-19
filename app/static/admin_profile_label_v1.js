(() => {
  function applyAdminProfileLabel() {
    const profile = document.querySelector('.sidebar .profile');
    if (!profile || profile.dataset.adminProfileLabel === '1') return;

    profile.dataset.adminProfileLabel = '1';
    profile.innerHTML = '<div class="avatar">A</div><div><strong>Admin</strong></div>';
    profile.setAttribute('aria-label', 'Admin');
  }

  const observer = new MutationObserver(applyAdminProfileLabel);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', applyAdminProfileLabel);
  window.addEventListener('hashchange', () => setTimeout(applyAdminProfileLabel, 0));
  applyAdminProfileLabel();
})();
