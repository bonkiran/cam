(() => {
  const token = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop() || '');
  const $ = (s, r = document) => r.querySelector(s);

  function esc(v = '') {
    return String(v ?? '').replace(/[&<>'\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));
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
    const dateOnly = String(value).slice(0, 10);
    const date = new Date(`${dateOnly}T12:00:00`);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'});
  }

  async function request(url, options = {}) {
    const res = await fetch(url, {
      cache:'no-store',
      ...options,
      headers:{'Content-Type':'application/json', ...(options.headers || {})},
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

  function ensureStyles() {
    if (document.querySelector('link[data-cam-slice2d]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/academy_enrollment_complete_v1.css?v=1';
    link.dataset.camSlice2d = '1';
    document.head.appendChild(link);
  }

  function hideFlowCards() {
    ['#welcomeCard','#nextCard','#agreementsCard','#documentsAcceptedCard','#paymentCard','#paymentCompleteCard','#enrollmentCompleteCard'].forEach(selector => {
      const node = $(selector);
      if (node) node.hidden = true;
    });
  }

  function renderSteps(completed) {
    const host = $('#enrollmentSteps');
    if (!host) return;
    const steps = [
      ['Enrollment Summary','done'],
      ['Agreements & Documents','done'],
      ['Fees & Payment','done'],
      ['Complete', completed ? 'done' : 'current'],
    ];
    host.innerHTML = steps.map(([label, state], index) => {
      const marker = state === 'done' ? '✓' : String(index + 1);
      return `<div class="step ${state}"><span>${marker}</span><div><strong>${esc(label)}</strong><small>${state === 'done' ? 'Completed' : 'Current step'}</small></div></div>`;
    }).join('');
  }

  function setStatus(label) {
    const node = $('#enrollmentStatus');
    if (node) node.textContent = label;
  }

  function ensureCompleteButton() {
    const card = $('#paymentCompleteCard');
    if (!card || $('#completeEnrollment')) return;
    const old = $('.coming-soon', card);
    const button = document.createElement('button');
    button.id = 'completeEnrollment';
    button.type = 'button';
    button.className = 'complete-enrollment-button';
    button.textContent = 'Complete Enrollment';
    button.addEventListener('click', completeEnrollment);
    if (old) old.replaceWith(button);
    else card.appendChild(button);

    const note = document.createElement('p');
    note.className = 'completion-handoff-note';
    note.textContent = 'Completing enrollment finalizes this record and makes the player ready for academy Program / Batch assignment.';
    button.insertAdjacentElement('afterend', note);
  }

  function ensureCompletionCard() {
    let card = $('#enrollmentCompleteCard');
    if (card) return card;
    card = document.createElement('section');
    card.id = 'enrollmentCompleteCard';
    card.className = 'card final-completion-card';
    card.hidden = true;
    $('#paymentCompleteCard')?.insertAdjacentElement('afterend', card);
    return card;
  }

  function documentRows(documents = []) {
    if (!documents.length) return '<p class="completion-muted">No accepted documents were found.</p>';
    return documents.map(doc => `
      <div class="completion-document-row">
        <div><strong>${esc(doc.title)}</strong><small>Version ${esc(doc.version)} · Accepted ${esc(dateLabel(doc.accepted_at))}</small></div>
        <a class="doc-button" href="${esc(doc.download_url)}">Download</a>
      </div>`).join('');
  }

  function showCompleted(data) {
    hideFlowCards();
    const card = ensureCompletionCard();
    const payment = data.payment || {};
    const brand = String(payment.card_brand || 'Card');
    const masked = payment.card_last4 ? `${brand.charAt(0).toUpperCase()}${brand.slice(1)} •••• ${payment.card_last4}` : 'Saved securely';
    card.innerHTML = `
      <div class="final-check">✓</div>
      <span class="kicker light">PROCESS 2 COMPLETE</span>
      <h2>Enrollment complete</h2>
      <p>${esc(data.player?.name || 'The player')} has completed CAM enrollment. The academy can now assign the appropriate Program and Batch.</p>
      <div class="completion-summary-grid">
        <div><span>Player</span><strong>${esc(data.player?.name || '—')}</strong></div>
        <div><span>Completed</span><strong>${esc(dateLabel(data.completed_at))}</strong></div>
        <div><span>Monthly Tuition</span><strong>${esc(money(payment.monthly_amount_cents, payment.currency))}</strong></div>
        <div><span>First Payment</span><strong>${esc(dateLabel(payment.billing_start_date))}</strong></div>
        <div><span>Saved Method</span><strong>${esc(masked)}</strong></div>
        <div><span>Next Step</span><strong>Program / Batch Assignment</strong></div>
      </div>
      <div class="completion-package-actions">
        <a class="completion-package-button" href="${esc(data.package_url || '#')}">Download Enrollment Package</a>
        <span>Includes the accepted PDFs, enrollment confirmation and acceptance summary.</span>
      </div>
      <section class="completion-documents">
        <h3>Your Enrollment Documents</h3>
        ${documentRows(data.documents || [])}
      </section>
      <div class="completion-info-note">No Program or Batch is assigned automatically. Academy staff will complete placement separately.</div>
    `;
    card.hidden = false;
    setStatus('Complete');
    renderSteps(true);
    window.scrollTo({top:0, behavior:'smooth'});
  }

  function showPaymentMethodAdded(data) {
    const card = $('#paymentCompleteCard');
    if (!card) return;
    hideFlowCards();
    card.hidden = false;
    const payment = data.payment || data.authorization || {};
    const brand = String(payment.card_brand || 'Card');
    const last4 = payment.card_last4 ? `•••• ${payment.card_last4}` : 'saved securely';
    const savedMethod = $('#savedPaymentMethod');
    const firstPayment = $('#savedFirstPayment');
    if (savedMethod) savedMethod.textContent = `${brand.charAt(0).toUpperCase()}${brand.slice(1)} ${last4}`;
    if (firstPayment) firstPayment.textContent = `${dateLabel(payment.billing_start_date)} · ${money(payment.monthly_amount_cents, payment.currency || 'USD')}`;
    setStatus('Payment Method Added');
    renderSteps(false);
    ensureCompleteButton();
  }

  async function completeEnrollment(event) {
    const button = event?.currentTarget || $('#completeEnrollment');
    if (!button) return;
    button.disabled = true;
    button.textContent = 'Completing enrollment…';
    try {
      const data = await request(`/api/public/enrollment/${encodeURIComponent(token)}/complete`, {method:'POST', body:'{}'});
      showCompleted(data);
    } catch (err) {
      button.disabled = false;
      button.textContent = 'Complete Enrollment';
      alert(err.message);
    }
  }

  async function reconcileStage() {
    if (!token) return;
    try {
      const enrollmentData = await request(`/api/public/enrollment/${encodeURIComponent(token)}`);
      if (enrollmentData?.enrollment?.status === 'completed') {
        const completion = await request(`/api/public/enrollment/${encodeURIComponent(token)}/completion`);
        showCompleted(completion);
        return;
      }
      const payment = await request(`/api/public/enrollment/${encodeURIComponent(token)}/payment`);
      if (payment?.authorization?.setup_status === 'succeeded') {
        try {
          const completion = await request(`/api/public/enrollment/${encodeURIComponent(token)}/completion`);
          showPaymentMethodAdded(completion);
        } catch {
          showPaymentMethodAdded(payment);
        }
      }
    } catch {
      // The main Slice 2A-2C script owns initial error handling. Slice 2D only
      // reconciles the stage when payment/completion data are available.
    }
  }

  function observePaymentCompletion() {
    const card = $('#paymentCompleteCard');
    if (!card) return;
    const observer = new MutationObserver(() => {
      if (!card.hidden) ensureCompleteButton();
    });
    observer.observe(card, {attributes:true, attributeFilter:['hidden']});
    if (!card.hidden) ensureCompleteButton();
  }

  ensureStyles();
  window.addEventListener('load', () => {
    observePaymentCompletion();
    setTimeout(reconcileStage, 350);
  });
})();