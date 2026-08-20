(() => {
  const PHONE_CHARS = /^\+?[0-9 ()\-.]+$/;
  const MESSAGE = 'Enter a valid phone number using 7–15 digits. You may use spaces, parentheses, +, - or periods.';

  function validPhone(value) {
    const text = String(value || '').trim();
    if (!text || !PHONE_CHARS.test(text)) return false;
    const digits = text.replace(/\D/g, '');
    return digits.length >= 7 && digits.length <= 15;
  }

  function configure(input, required) {
    if (!input || input.dataset.phoneValidationBound === '1') return;
    input.dataset.phoneValidationBound = '1';
    input.inputMode = 'tel';
    input.autocomplete = input.name === 'parent_phone' ? 'tel' : 'tel';

    const validate = () => {
      const value = input.value.trim();
      if (!value && !required) {
        input.setCustomValidity('');
        return true;
      }
      const ok = validPhone(value);
      input.setCustomValidity(ok ? '' : MESSAGE);
      return ok;
    };

    input.addEventListener('input', validate);
    input.addEventListener('change', validate);
    input.addEventListener('blur', validate);
    input._camValidatePhone = validate;
  }

  function apply() {
    const form = document.querySelector('#registrationForm');
    if (!form) return;

    configure(form.querySelector('[name="parent_phone"]'), true);
    form.querySelectorAll('[data-emergency]').forEach((card, index) => {
      configure(card.querySelector('[data-contact="phone"]'), index === 0);
    });

    if (form.dataset.phoneValidationSubmitBound !== '1') {
      form.dataset.phoneValidationSubmitBound = '1';
      form.addEventListener('submit', () => {
        form.querySelectorAll('[name="parent_phone"], [data-emergency] [data-contact="phone"]').forEach(input => {
          input._camValidatePhone?.();
        });
      }, true);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
})();
