(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const token = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop() || '');
  let currentEnrollment = null;
  let currentSteps = [];
  let currentDocuments = [];

  function esc(v = '') {
    return String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
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
      completed:'Complete'
    };
    return map[status] || status || '—';
  }

  async function request(url, options = {}) {
    const res = await fetch(url, {
      cache: 'no-store',
      ...options,
      headers: {'Content-Type':'application/json', ...(options.headers || {})},
    });
    let data = null;
    try { data = await res.json(); } catch {}
    if (!res.ok) throw new Error(data?.detail || `Request failed (${res.status})`);
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

  function setMainStatus(status) {
    if (currentEnrollment) currentEnrollment.status = status;
    $('#enrollmentStatus').textContent = statusLabel(status);
  }

  function hideFlowCards() {
    ['#welcomeCard', '#nextCard', '#agreementsCard', '#documentsAcceptedCard'].forEach(selector => {
      const node = $(selector);
      if (node) node.hidden = true;
    });
  }

  function showStageForStatus(status) {
    hideFlowCards();
    if (status === 'documents_accepted' || status === 'completed') {
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

  $('#startEnrollment')?.addEventListener('click', e => startEnrollment(e.currentTarget));
  $('#openAgreements')?.addEventListener('click', openAgreements);
  $('#acceptAgreements')?.addEventListener('click', acceptAgreements);

  load();
})();
