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
    input.title = PHONE_MESSAGE;
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
    input.title = STATE_MESSAGE;
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
    input.pattern = '[0-9]{5}';
    input.title = ZIP_MESSAGE;
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
    if (label) label.remove();
  }

  function academyLabel(name) {
    const clean = String(name || 'Academy').trim() || 'Academy';
    return /academy$/i.test(clean) ? clean : `${clean} Academy`;
  }

  async function applyBranding() {
    if (document.documentElement.dataset.registrationBrandingApplied === '1') return;
    document.documentElement.dataset.registrationBrandingApplied = '1';
    const token = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop() || '');
    if (!token) return;
    try {
      const response = await fetch(`/api/public/registration/${encodeURIComponent(token)}/branding`, {cache:'no-store'});
      if (!response.ok) return;
      const data = await response.json();
      const title = `${academyLabel(data?.academy_name)} Player Registration`;
      const heading = document.querySelector('.registration-intro h1');
      if (heading) heading.textContent = title;
      const brandSubtitle = document.querySelector('.registration-brand small');
      if (brandSubtitle) brandSubtitle.textContent = title;
      document.title = `${title} · CrickAnalysis`;
    } catch (error) {
      console.warn('Registration branding unavailable', error);
    }
  }

  function addAddressVerificationNote(form) {
    if (form.querySelector('[data-address-verification-note]')) return;
    const parentSection = form.querySelector('[name="parent_address_line1"]')?.closest('.form-section');
    const grid = parentSection?.querySelector('.form-grid');
    if (!grid) return;
    const note = document.createElement('p');
    note.dataset.addressVerificationNote = '1';
    note.className = 'save-state';
    note.textContent = 'Address, city, state and ZIP are verified together as one U.S. address when you submit.';
    grid.insertAdjacentElement('afterend', note);
  }

  function apply() {
    const form = document.querySelector('#registrationForm');
    applyBranding();
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
    addAddressVerificationNote(form);

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
