(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const token = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop() || '');
  let currentEnrollment = null;
  let currentSteps = [];
  let currentDocuments = [];
  let paymentSummary = null;
  let paymentSetup = null;
  let stripe = null;
  let stripeElements = null;

  function esc(v = '') {
    return String(v ?? '').replace(/[&<>'\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));
  }

  function academyLabel(name) {
    const clean = String(name || 'Academy').trim() || 'Academy';
    return /academy$/i.test(clean) ? clean : `${clean} Academy`;
  }

  function statusLabel(status) {
    const map = {
      created:'Link Created',
      sent:'Sent',
      opened:'Opened',
      in_progress:'In Progress',
      documents_accepted:'Documents Accepted',
      payment_method_added:'Payment Method Added',
      completed:'Complete'
    };
    return map[status] || status || '—';
  }

  function money(cents, currency = 'USD') {
    const value = Number(cents || 0) / 100;
    try {
      return new Intl.NumberFormat('en-US', {style:'currency', currency}).format(value);
    } catch {
      return `$${value.toFixed(2)}`;
    }
  }

  function dateLabel(value) {
    if (!value) return '—';
    const date = new Date(`${value}T12:00:00`);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'});
  }

  async function request(url, options = {}) {
    const res = await fetch(url, {
      cache: 'no-store',
      ...options,
      headers: {'Content-Type':'application/json', ...(options.headers || {})},
    });
    let data = null;
    try { data = await res.json(); } catch {}
    if (!res.ok) {
      const detail = data?.detail;
      const message = typeof detail === 'string' ? detail : detail?.message || `Request failed (${res.status})`;
      throw new Error(message);
    }
    return data;
  }

  function renderSteps(steps = []) {
    const host = $('#enrollmentSteps');
    if (!host) return;
    host.innerHTML = steps.map((step, index) => {
      const state = step.status || 'later';
      const marker = state === 'done' ? '✓' : String(index + 1);
      return `<div class="step ${esc(state)}"><span>${marker}</span><div><strong>${esc(step.label)}</strong><small>${state === 'done' ? 'Completed' : state === 'current' ? 'Current step' : 'Upcoming'}</small></div></div>`;
    }).join('');
  }

  function renderPaymentCompletedSteps() {
    renderSteps([
      {key:'summary', label:'Enrollment Summary', status:'done'},
      {key:'agreements', label:'Agreements & Documents', status:'done'},
      {key:'payment', label:'Fees & Payment', status:'done'},
      {key:'complete', label:'Complete', status:'current'},
    ]);
  }

  function setMainStatus(status) {
    if (currentEnrollment) currentEnrollment.status = status;
    $('#enrollmentStatus').textContent = statusLabel(status);
  }

  function hideFlowCards() {
    ['#welcomeCard', '#nextCard', '#agreementsCard', '#documentsAcceptedCard', '#paymentCard', '#paymentCompleteCard'].forEach(selector => {
      const node = $(selector);
      if (node) node.hidden = true;
    });
  }

  function showStageForStatus(status) {
    hideFlowCards();
    if (status === 'completed') {
      $('#paymentCompleteCard').hidden = false;
    } else if (status === 'documents_accepted') {
      $('#documentsAcceptedCard').hidden = false;
    } else if (status === 'in_progress') {
      $('#nextCard').hidden = false;
    } else {
      $('#welcomeCard').hidden = false;
    }
  }

  async function refreshEnrollment() {
    const data = await request(`/api/public/enrollment/${encodeURIComponent(token)}`);
    currentEnrollment = data?.enrollment || {};
    currentSteps = data?.steps || [];
    const academy = academyLabel(currentEnrollment.academy_name);
    document.title = `${academy} Parent Enrollment`;
    $('#enrollmentTitle').textContent = `${academy} Parent Enrollment`;
    $('#enrollmentSubtitle').textContent = `Complete the remaining enrollment steps for ${currentEnrollment.player_name || 'your player'}.`;
    $('#enrollmentPlayer').textContent = currentEnrollment.player_name || '—';
    $('#enrollmentParent').textContent = [currentEnrollment.parent_first_name, currentEnrollment.parent_last_name].filter(Boolean).join(' ') || '—';
    $('#enrollmentStatus').textContent = statusLabel(currentEnrollment.status);
    renderSteps(currentSteps);
    return data;
  }

  async function load() {
    if (!token) return showError('The enrollment link is incomplete.');
    try {
      await refreshEnrollment();
      $('#enrollmentLoading').hidden = true;
      $('#enrollmentPortal').hidden = false;
      showStageForStatus(currentEnrollment.status);
    } catch (err) {
      showError(err.message);
    }
  }

  function showError(message) {
    $('#enrollmentLoading').hidden = true;
    $('#enrollmentPortal').hidden = true;
    $('#enrollmentError').hidden = false;
    $('#enrollmentErrorText').textContent = message;
  }

  async function startEnrollment(button) {
    button.disabled = true;
    button.textContent = 'Starting…';
    try {
      await request(`/api/public/enrollment/${encodeURIComponent(token)}/start`, {method:'POST', body:'{}'});
      await refreshEnrollment();
      showStageForStatus('in_progress');
      window.scrollTo({top:0, behavior:'smooth'});
    } catch (err) {
      button.disabled = false;
      button.textContent = 'Start Enrollment';
      alert(err.message);
    }
  }

  function documentCard(documentItem, index) {
    const testBadge = documentItem.test_only ? '<span class="doc-test">TEST SAMPLE</span>' : '';
    const viewedLabel = documentItem.viewed ? 'Viewed' : 'Open PDF to review';
    return `<article class="document-item" data-document-id="${documentItem.id}">
      <div class="document-number">${index + 1}</div>
      <div class="document-body">
        <div class="document-title-row"><h3>${esc(documentItem.title)}</h3>${testBadge}</div>
        <div class="document-meta">Version ${esc(documentItem.version)} · ${documentItem.required ? 'Required' : 'Optional'} · <span data-view-status>${esc(viewedLabel)}</span></div>
        <div class="document-actions">
          <a class="doc-button primary-link" target="_blank" rel="noopener" href="${esc(documentItem.view_url)}" data-doc-view="${documentItem.id}">View PDF</a>
          <a class="doc-button" href="${esc(documentItem.download_url)}" data-doc-download="${documentItem.id}">Download</a>
        </div>
        <label class="document-accept">
          <input type="checkbox" data-doc-accept="${documentItem.id}" ${documentItem.accepted ? 'checked disabled' : ''}/>
          <span>I have reviewed and agree to this document.</span>
        </label>
        ${documentItem.accepted ? `<small class="accepted-note">Accepted${documentItem.signer_name ? ` by ${esc(documentItem.signer_name)}` : ''}.</small>` : ''}
      </div>
    </article>`;
  }

  function wireDocumentViewTracking() {
    document.querySelectorAll('[data-doc-view]').forEach(link => {
      link.addEventListener('click', () => {
        const card = link.closest('.document-item');
        const status = $('[data-view-status]', card);
        if (status) status.textContent = 'Viewed';
        const id = Number(link.dataset.docView);
        const item = currentDocuments.find(doc => Number(doc.id) === id);
        if (item) item.viewed = true;
      });
    });
    document.querySelectorAll('[data-doc-download]').forEach(link => {
      link.addEventListener('click', () => {
        const card = link.closest('.document-item');
        const status = $('[data-view-status]', card);
        if (status) status.textContent = 'Viewed';
        const id = Number(link.dataset.docDownload);
        const item = currentDocuments.find(doc => Number(doc.id) === id);
        if (item) item.viewed = true;
      });
    });
  }

  async function openAgreements() {
    const nextButton = $('#openAgreements');
    if (nextButton) {
      nextButton.disabled = true;
      nextButton.textContent = 'Loading…';
    }
    try {
      const data = await request(`/api/public/enrollment/${encodeURIComponent(token)}/documents`);
      currentDocuments = data?.documents || [];
      const host = $('#agreementDocuments');
      host.innerHTML = currentDocuments.map(documentCard).join('');
      wireDocumentViewTracking();
      $('#nextCard').hidden = true;
      $('#agreementsCard').hidden = false;
      $('#agreementsCard').scrollIntoView({behavior:'smooth', block:'start'});
    } catch (err) {
      if (nextButton) {
        nextButton.disabled = false;
        nextButton.textContent = 'Continue to Agreements & Documents';
      }
      alert(err.message);
    }
  }

  async function acceptAgreements() {
    const button = $('#acceptAgreements');
    const error = $('#agreementError');
    error.hidden = true;
    error.textContent = '';

    const acceptedIds = [...document.querySelectorAll('[data-doc-accept]:checked')]
      .map(input => Number(input.dataset.docAccept));
    const signerName = $('#legalSignerName').value.trim();
    const consent = $('#electronicSignatureConsent').checked;

    if (acceptedIds.length < currentDocuments.filter(doc => doc.required).length) {
      error.textContent = 'Please accept each required document.';
      error.hidden = false;
      return;
    }
    if (!signerName || signerName.split(/\s+/).length < 2) {
      error.textContent = 'Enter the parent/guardian full legal name.';
      error.hidden = false;
      return;
    }
    if (!consent) {
      error.textContent = 'Electronic signature consent is required.';
      error.hidden = false;
      return;
    }

    button.disabled = true;
    button.textContent = 'Recording acceptance…';
    try {
      await request(`/api/public/enrollment/${encodeURIComponent(token)}/agreements/accept`, {
        method:'POST',
        body:JSON.stringify({
          document_ids: acceptedIds,
          signer_name: signerName,
          electronic_signature_consent: consent,
        }),
      });
      await refreshEnrollment();
      setMainStatus('documents_accepted');
      hideFlowCards();
      $('#documentsAcceptedCard').hidden = false;
      window.scrollTo({top:0, behavior:'smooth'});
    } catch (err) {
      button.disabled = false;
      button.textContent = 'Agree & Continue';
      error.textContent = err.message;
      error.hidden = false;
    }
  }

  function addressText(address = {}) {
    return [
      address.address_line1,
      address.address_line2,
      [address.city, address.state, address.postal_code].filter(Boolean).join(', ').replace(', ,', ','),
      address.country,
    ].filter(Boolean).join('\n');
  }

  function showPaymentError(message) {
    const error = $('#paymentError');
    error.textContent = message;
    error.hidden = false;
  }

  function clearPaymentError() {
    const error = $('#paymentError');
    error.hidden = true;
    error.textContent = '';
  }

  function renderPaymentSummary(data) {
    paymentSummary = data;
    const plan = data.plan || {};
    const provider = data.provider || {};
    $('#paymentFeePlan').textContent = plan.fee_plan_name || 'Monthly Tuition';
    $('#paymentMonthlyAmount').textContent = money(plan.monthly_amount_cents, plan.currency);
    $('#paymentDueToday').textContent = money(plan.due_today_cents, plan.currency);
    $('#paymentFirstCharge').textContent = dateLabel(plan.billing_start_date);
    $('#paymentProviderName').textContent = `${provider.display_name || provider.name || 'Payment Provider'} ${String(provider.environment || '').toLowerCase() === 'sandbox' ? 'Sandbox' : ''}`.trim();
    $('#paymentEnvironmentBadge').textContent = String(provider.environment || 'sandbox').toUpperCase();
    $('#recurringConsentText').textContent = data.recurring_consent_text || '';
    $('#parentBillingAddress').textContent = addressText(data.parent_address || {}) || 'Verified parent address unavailable.';

    if (data.authorization?.setup_status === 'succeeded') {
      showPaymentComplete(data);
    }
  }

  async function openPayment() {
    const button = $('#openPayment');
    if (button) {
      button.disabled = true;
      button.textContent = 'Loading…';
    }
    clearPaymentError();
    try {
      const data = await request(`/api/public/enrollment/${encodeURIComponent(token)}/payment`);
      renderPaymentSummary(data);
      hideFlowCards();
      if (data.authorization?.setup_status === 'succeeded') {
        showPaymentComplete(data);
      } else {
        $('#paymentCard').hidden = false;
        $('#paymentCard').scrollIntoView({behavior:'smooth', block:'start'});
      }
    } catch (err) {
      if (button) {
        button.disabled = false;
        button.textContent = 'Continue to Fees & Payment';
      }
      alert(err.message);
    }
  }

  function billingPayload() {
    if ($('#useParentBillingAddress').checked) {
      return {use_parent_address:true, billing_address:null};
    }
    return {
      use_parent_address:false,
      billing_address:{
        address_line1:$('#billingAddress1').value.trim(),
        address_line2:$('#billingAddress2').value.trim() || null,
        city:$('#billingCity').value.trim(),
        state:$('#billingState').value.trim(),
        postal_code:$('#billingZip').value.trim(),
        country:'United States',
      },
    };
  }

  function loadStripeScript() {
    if (window.Stripe) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-cam-stripe-js]');
      if (existing) {
        existing.addEventListener('load', resolve, {once:true});
        existing.addEventListener('error', () => reject(new Error('Stripe secure payment library could not load.')), {once:true});
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://js.stripe.com/v3/';
      script.async = true;
      script.dataset.camStripeJs = '1';
      script.onload = resolve;
      script.onerror = () => reject(new Error('Stripe secure payment library could not load.'));
      document.head.appendChild(script);
    });
  }

  async function beginPaymentSetup() {
    clearPaymentError();
    const button = $('#beginPaymentSetup');
    if (!$('#recurringPaymentConsent').checked) {
      return showPaymentError('Please authorize the recurring monthly tuition schedule before continuing.');
    }
    button.disabled = true;
    button.textContent = 'Preparing secure payment…';
    try {
      const address = billingPayload();
      const data = await request(`/api/public/enrollment/${encodeURIComponent(token)}/payment/setup`, {
        method:'POST',
        body:JSON.stringify({recurring_consent:true, ...address}),
      });
      paymentSetup = data;
      if (data.already_configured) {
        renderPaymentSummary(data);
        return;
      }
      if (data.provider !== 'stripe') {
        throw new Error('The selected provider is compatible with CAM, but this Slice 2C parent card-entry screen currently has Stripe Sandbox enabled first.');
      }
      const publishableKey = data.client_config?.publishable_key;
      if (!publishableKey || !data.client_secret) throw new Error('Stripe Sandbox client configuration is incomplete.');
      await loadStripeScript();
      stripe = window.Stripe(publishableKey);
      stripeElements = stripe.elements({clientSecret:data.client_secret});
      const element = stripeElements.create('payment', {layout:'tabs'});
      $('#paymentElement').innerHTML = '';
      element.mount('#paymentElement');
      $('#providerPaymentPanel').hidden = false;
      button.hidden = true;
      $('#providerPaymentPanel').scrollIntoView({behavior:'smooth', block:'center'});
    } catch (err) {
      button.disabled = false;
      button.textContent = 'Continue to Secure Payment Method';
      showPaymentError(err.message);
    }
  }

  async function confirmPaymentSetup() {
    clearPaymentError();
    const button = $('#confirmPaymentSetup');
    if (!stripe || !stripeElements || !paymentSetup) {
      return showPaymentError('Secure payment setup is not ready. Please start again.');
    }
    button.disabled = true;
    button.textContent = 'Saving payment method…';
    try {
      const result = await stripe.confirmSetup({elements:stripeElements, redirect:'if_required'});
      if (result.error) throw new Error(result.error.message || 'Stripe could not save the payment method.');
      if (!result.setupIntent || result.setupIntent.status !== 'succeeded') {
        throw new Error('Stripe payment-method setup is not complete.');
      }
      const data = await request(`/api/public/enrollment/${encodeURIComponent(token)}/payment/complete`, {
        method:'POST',
        body:JSON.stringify({setup_payload:{setup_session_id:paymentSetup.setup_session_id}}),
      });
      showPaymentComplete(data);
    } catch (err) {
      button.disabled = false;
      button.textContent = 'Save Payment Method & Continue';
      showPaymentError(err.message);
    }
  }

  function showPaymentComplete(data) {
    paymentSummary = data;
    const auth = data.authorization || {};
    const plan = data.plan || {};
    const brand = String(auth.card_brand || 'Card');
    const last4 = auth.card_last4 ? `•••• ${auth.card_last4}` : 'saved securely';
    $('#savedPaymentMethod').textContent = `${brand.charAt(0).toUpperCase()}${brand.slice(1)} ${last4}`;
    $('#savedFirstPayment').textContent = `${dateLabel(auth.billing_start_date || plan.billing_start_date)} · ${money(auth.monthly_amount_cents ?? plan.monthly_amount_cents, plan.currency)}`;
    hideFlowCards();
    $('#paymentCompleteCard').hidden = false;
    setMainStatus('payment_method_added');
    renderPaymentCompletedSteps();
    window.scrollTo({top:0, behavior:'smooth'});
  }

  $('#startEnrollment')?.addEventListener('click', e => startEnrollment(e.currentTarget));
  $('#openAgreements')?.addEventListener('click', openAgreements);
  $('#acceptAgreements')?.addEventListener('click', acceptAgreements);
  $('#openPayment')?.addEventListener('click', openPayment);
  $('#useParentBillingAddress')?.addEventListener('change', e => {
    $('#alternateBillingAddress').hidden = e.currentTarget.checked;
    $('#parentBillingAddress').hidden = !e.currentTarget.checked;
  });
  $('#beginPaymentSetup')?.addEventListener('click', beginPaymentSetup);
  $('#confirmPaymentSetup')?.addEventListener('click', confirmPaymentSetup);

  load();
})();
