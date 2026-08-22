(() => {
  function normalizeWebsite(raw) {
    const value = String(raw || '').trim();
    if (!value) return '';
    if (/^https?:\/\//i.test(value)) return value;
    return `https://${value}`;
  }

  function isValidWebsite(raw) {
    const value = normalizeWebsite(raw);
    if (!value) return true;
    try {
      const parsed = new URL(value);
      return (parsed.protocol === 'http:' || parsed.protocol === 'https:') && Boolean(parsed.hostname) && (parsed.hostname.includes('.') || parsed.hostname === 'localhost');
    } catch {
      return false;
    }
  }

  function enhanceNameField(formSelector, label) {
    const form = document.querySelector(formSelector);
    const input = form?.querySelector('input[name="name"]');
    if (!input || input.dataset.nameValidationEnhanced === '1') return;
    input.dataset.nameValidationEnhanced = '1';
    input.minLength = 2;
    input.maxLength = 160;
    input.addEventListener('input', () => input.setCustomValidity(''));
    input.addEventListener('invalid', () => {
      if (input.validity.valueMissing) input.setCustomValidity(`${label} is required.`);
      else if (input.validity.tooShort) input.setCustomValidity(`${label} must be at least 2 characters.`);
    });
  }

  function enhanceNameFields() {
    enhanceNameField('#camProfileForm', 'Academy Name');
    enhanceNameField('#camPlayerForm', 'Player name');
  }

  function enhanceWebsiteField(root = document) {
    const form = root.querySelector?.('#camProfileForm');
    const input = form?.querySelector('input[name="website"]');
    if (!form || !input || input.dataset.websiteValidationEnhanced === '1') return;

    input.dataset.websiteValidationEnhanced = '1';
    input.type = 'text';
    input.inputMode = 'url';
    input.autocomplete = 'url';
    input.placeholder = 'academy.com or www.academy.com';

    const clearError = () => input.setCustomValidity('');
    input.addEventListener('input', clearError);
    input.addEventListener('blur', () => {
      const raw = input.value.trim();
      if (!raw) {
        clearError();
        return;
      }
      if (!isValidWebsite(raw)) {
        input.setCustomValidity('Enter a valid website, for example academy.com or https://academy.com.');
        input.reportValidity();
        return;
      }
      clearError();
      input.value = normalizeWebsite(raw);
    });

    form.addEventListener('submit', (event) => {
      const raw = input.value.trim();
      if (!raw) {
        clearError();
        return;
      }
      if (!isValidWebsite(raw)) {
        input.setCustomValidity('Enter a valid website, for example academy.com or https://academy.com.');
        input.reportValidity();
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
      clearError();
      input.value = normalizeWebsite(raw);
    }, true);
  }

  function enhanceAll() {
    enhanceWebsiteField(document);
    enhanceNameFields();
  }

  function install() {
    enhanceAll();
    const observer = new MutationObserver(enhanceAll);
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  const api = { normalizeWebsite, isValidWebsite };
  if (typeof globalThis !== 'undefined') globalThis.CrickAcademyValidation = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
    else install();
  }
})();
