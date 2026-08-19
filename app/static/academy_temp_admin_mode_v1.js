(() => {
  const SESSION_KEY = 'cam-academy-session-v1';

  async function enableTemporaryAdminMode() {
    try {
      const response = await fetch('/api/cam-mode', { cache: 'no-store' });
      if (!response.ok) return;
      const mode = await response.json();
      if (!mode?.temporary_admin_mode) return;

      // This is only a browser marker. The server-side temporary Admin mode is
      // what authorizes the controlled pilot. No credential or secret is stored.
      sessionStorage.setItem(SESSION_KEY, 'temporary-admin-mode');
      window.CAM_TEMP_ADMIN_MODE = true;

      // CAM-13 may have rendered once before this lightweight mode check returns.
      // Trigger its normal route re-application so the seven-item Owner/Admin
      // console replaces the legacy Academy tabs immediately.
      window.dispatchEvent(new Event('hashchange'));
    } catch (error) {
      console.warn('Temporary Admin mode could not initialize.', error);
    }
  }

  enableTemporaryAdminMode();
})();
