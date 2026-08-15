(() => {
  function resetPlayerField() {
    const form = document.querySelector('#uploadForm');
    if (!form || form.dataset.playerFieldReset === '1') return;
    const input = form.querySelector('input[name="player_name"]');
    if (!input) return;
    input.value = '';
    input.placeholder = 'Enter player name';
    input.autocomplete = 'off';
    form.dataset.playerFieldReset = '1';
  }

  const observer = new MutationObserver(resetPlayerField);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('hashchange', () => setTimeout(resetPlayerField, 0));
  resetPlayerField();
})();
