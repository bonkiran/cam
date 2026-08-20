(() => {
  const STATES = {
    AL:'Alabama',AK:'Alaska',AZ:'Arizona',AR:'Arkansas',CA:'California',CO:'Colorado',CT:'Connecticut',DE:'Delaware',FL:'Florida',GA:'Georgia',HI:'Hawaii',ID:'Idaho',IL:'Illinois',IN:'Indiana',IA:'Iowa',KS:'Kansas',KY:'Kentucky',LA:'Louisiana',ME:'Maine',MD:'Maryland',MA:'Massachusetts',MI:'Michigan',MN:'Minnesota',MS:'Mississippi',MO:'Missouri',MT:'Montana',NE:'Nebraska',NV:'Nevada',NH:'New Hampshire',NJ:'New Jersey',NM:'New Mexico',NY:'New York',NC:'North Carolina',ND:'North Dakota',OH:'Ohio',OK:'Oklahoma',OR:'Oregon',PA:'Pennsylvania',RI:'Rhode Island',SC:'South Carolina',SD:'South Dakota',TN:'Tennessee',TX:'Texas',UT:'Utah',VT:'Vermont',VA:'Virginia',WA:'Washington',WV:'West Virginia',WI:'Wisconsin',WY:'Wyoming',DC:'District of Columbia'
  };
  const LOOKUP = new Map();
  Object.entries(STATES).forEach(([code, name]) => {
    LOOKUP.set(code.toLowerCase(), code);
    LOOKUP.set(name.toLowerCase(), code);
  });

  const STATE_MESSAGE = 'Enter a valid US state using its 2-letter abbreviation or full state name.';
  const ZIP_MESSAGE = 'Enter a valid 5-digit US ZIP code.';

  function normalizeState(value) {
    const text = String(value || '').trim().toLowerCase();
    return LOOKUP.get(text) || null;
  }

  function configureState(input) {
    if (!input || input.dataset.usStateValidationBound === '1') return;
    input.dataset.usStateValidationBound = '1';
    const validate = () => {
      const text = input.value.trim();
      const code = normalizeState(text);
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

  function apply() {
    const form = document.querySelector('#registrationForm');
    if (!form) return;
    const state = form.querySelector('[name="parent_state"]');
    const zip = form.querySelector('[name="parent_postal_code"]');
    configureState(state);
    configureZip(zip);

    if (form.dataset.usAddressValidationSubmitBound !== '1') {
      form.dataset.usAddressValidationSubmitBound = '1';
      form.addEventListener('submit', () => {
        state?._camValidateUsState?.();
        zip?._camValidateUsZip?.();
      }, true);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply);
  else apply();
})();
