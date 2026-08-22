(() => {
  // Copying a registration URL is an internal clipboard action, not proof that
  // the parent received it. Intercept the legacy Copy Link handler before it
  // reaches the original target listener so the invite remains Link Created.
  document.addEventListener('click', async (event) => {
    const button = event.target?.closest?.('[data-share="copy"]');
    if (!button) return;
    const registrationPage = document.querySelector('.cam-registration-page');
    if (!registrationPage || !registrationPage.contains(button)) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    const url = button.closest('.cam-share-box')?.querySelector('.cam-share-url')?.textContent?.trim();
    if (!url) return;

    try {
      await navigator.clipboard.writeText(url);
      if (typeof window.toast === 'function') {
        window.toast('Registration link copied. Status remains Link Created until it is sent.');
      }
    } catch (error) {
      console.warn('Could not copy registration link', error);
      if (typeof window.toast === 'function') window.toast('Could not copy registration link.');
    }
  }, true);
})();
