(() => {
  const PHONE_CHARS = /^\+?[0-9 ()\-.]+$/;
  const PHONE_MESSAGE = 'Enter a valid phone number using 9–15 digits. You may use spaces, parentheses, +, - or periods.';
  const STATE_MESSAGE = 'Enter a valid US state using its 2-letter abbreviation or full state name.';
  const ZIP_MESSAGE = 'Enter a valid 5-digit US ZIP code.';
  const STATES = {
    AL:'Alabama',AK:'Alaska',AZ:'Arizona',AR:'Arkansas',CA:'California',CO:'Colorado',CT:'Connecticut',DE:'Delaware',FL:'Florida',GA:'Georgia',HI:'Hawaii',ID:'Idaho',IL:'Illinois',IN:'Indiana',IA:'Iowa',KS:'Kansas',KY:'Kentucky',LA:'Louisiana',ME:'Maine',MD:'Maryland',MA:'Massachusetts',MI:'Michigan',MN:'Minnesota',MS:'Mississippi',MO:'Missouri',MT:'Montana',NE:'Nebraska',NV:'Nevada',NH:'New Hampshire',NJ:'New Jersey',NM:'New Mexico',NY:'New York',NC:'North Carolina',ND:'North Dakota',OH:'Ohio',OK:'Oklahoma',OR:'Oregon',PA:'Pennsylvania',RI:'Rhode Island',SC:'South Carolina',SD:'South Dakota',TN:'Tennessee',TX:'Texas',UT:'Utah',VT:'Vermont',VA:'Virginia',WA:'Washington',WV:'West Virginia',WI:'Wisconsin',WY:'Wyoming',DC:'District of Columbia'
  };
  const STATE_LOOKUP = new Map();
  Object.entries(STATES).forEach(([code, name]) => {
    STATE_LOOKUP.set(code.toLowerCase(), code);
    STATE_LOOKUP.set(name.toLowerCase(), code);
  });

  function validPhone(value) {
    const text = String(value || '').trim();
    if (!text || !PHONE_CHARS.test(text)) return false;
    const digits = text.replace(/\D/g, '');
    return digits.length >= 9 && digits.length <= 15;
  }

  function configurePhone(input, required) {
    if (!input || input.dataset.phoneValidationBound === '1') return;
    input.dataset.phoneValidationBound = '1';
    input.inputMode = 'tel';
    input.autocomplete = 'tel';
    const validate = () => {
      const value = input.value.trim();
      if (!value && !required) {
        input.setCustomValidity('');
        return true;
      }
      const ok = validPhone(value);
      input.setCustomValidity(ok ? '' : PHONE_MESSAGE);
      return ok;
    };
    input.addEventListener('input', validate);
    input.addEventListener('change', validate);
    input.addEventListener('blur', validate);
    input._camValidatePhone = validate;
  }

  function normalizeState(value) {
    return STATE_LOOKUP.get(String(value || '').trim().toLowerCase()) || null;
  }

  function configureState(input) {
    if (!input || input.dataset.usStateValidationBound === '1') return;
    input.dataset.usStateValidationBound = '1';
    const validate = () => {
      const code = normalizeState(input.value);
      input.setCustomValidity(code ? '' : STATE_MESSAGE);
      return !!code;
    };
    input.addEventListener('input', validate);
    input.addEventListener('change', validate);
    input.addEventListener('blur', () => {
      const code = normalizeState(input.value);
      if (code) input.value = code;
      validate();
    });
    input._camValidateUsState = validate;
  }

  function configureZip(input) {
    if (!input || input.dataset.usZipValidationBound === '1') return;
    input.dataset.usZipValidationBound = '1';
    input.inputMode = 'numeric';
    input.maxLength = 5;
    const validate = () => {
      const ok = /^[0-9]{5}$/.test(input.value.trim());
      input.setCustomValidity(ok ? '' : ZIP_MESSAGE);
      return ok;
    };
    input.addEventListener('input', validate);
    input.addEventListener('change', validate);
    input.addEventListener('blur', validate);
    input._camValidateUsZip = validate;
  }

  function hidePickupOption(form) {
    const pickup = form.querySelector('[name="parent_pickup_authorized"]');
    if (!pickup) return;
    pickup.checked = true;
    const label = pickup.closest('label');
    if (label) label.hidden = true;
  }

  function apply() {
    const form = document.querySelector('#registrationForm');
    if (!form) return;

    configurePhone(form.querySelector('[name="parent_phone"]'), true);
    form.querySelectorAll('[data-emergency]').forEach((card, index) => {
      configurePhone(card.querySelector('[data-contact="phone"]'), index === 0);
    });
    const state = form.querySelector('[name="parent_state"]');
    const zip = form.querySelector('[name="parent_postal_code"]');
    configureState(state);
    configureZip(zip);
    hidePickupOption(form);

    if (form.dataset.registrationValidationSubmitBound !== '1') {
      form.dataset.registrationValidationSubmitBound = '1';
      form.addEventListener('submit', () => {
        form.querySelectorAll('[name="parent_phone"], [data-emergency] [data-contact="phone"]').forEach(input => input._camValidatePhone?.());
        state?._camValidateUsState?.();
        zip?._camValidateUsZip?.();
      }, true);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply);
  else apply();
})();
