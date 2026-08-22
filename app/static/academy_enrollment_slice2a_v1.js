(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  let camName = 'Academy';

  function esc(v = '') {
    return String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  async function requestJson(url, options = {}) {
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

  function notify(message) {
    if (typeof window.toast === 'function') window.toast(message);
    else console.log(message);
  }

  function camLabel(name = camName) {
    const clean = String(name || 'Academy').trim() || 'Academy';
    return /academy$/i.test(clean) ? clean : `${clean} Academy`;
  }

  function phoneDigits(v = '') {
    return String(v || '').replace(/\D/g, '');
  }

  function applicationId(review) {
    const kicker = review.querySelector('.cam-kicker')?.textContent || '';
    const match = kicker.match(/APPLICATION\s*#\s*(\d+)/i);
    return match ? Number(match[1]) : null;
  }

  function section(review, heading) {
    return [...review.querySelectorAll('.cam-review-section')].find(
      item => item.querySelector('h3')?.textContent?.trim() === heading
    ) || null;
  }

  function sectionValue(review, heading, label) {
    const root = section(review, heading);
    if (!root) return '';
    const dt = [...root.querySelectorAll('dt')].find(el => el.textContent.trim() === label);
    return dt?.nextElementSibling?.textContent?.trim() || '';
  }

  function playerName(review) {
    return review.querySelector('.cam-registration-head h2')?.textContent?.trim() || 'your player';
  }

  function parentName(review) {
    return sectionValue(review, 'Parent', 'Name') || 'Parent';
  }

  function parentPhone(review) {
    return sectionValue(review, 'Parent', 'Phone');
  }

  function parentEmail(review) {
    return sectionValue(review, 'Parent', 'Email');
  }

  async function markSent(enrollmentId, channel) {
    try {
      await requestJson(`/api/cam/enrollments/${enrollmentId}/sent`, {
        method: 'POST',
        body: JSON.stringify({channel}),
      });
    } catch (err) {
      console.warn('Could not mark enrollment link sent', err);
    }
  }

  function enrollmentMessage(review, enrollment) {
    return `Hi ${parentName(review)}, ${playerName(review)}'s registration with ${camLabel(enrollment.academy_name)} has been approved. Please complete enrollment securely in CAM using this link: ${enrollment.enrollment_url}`;
  }

  function showEnrollmentShare(review, enrollment) {
    let host = $('#camEnrollmentShare', review);
    if (!host) {
      host = document.createElement('div');
      host.id = 'camEnrollmentShare';
      host.style.marginTop = '14px';
      review.appendChild(host);
    }
    const message = enrollmentMessage(review, enrollment);
    const phone = phoneDigits(parentPhone(review));
    const email = parentEmail(review);
    const sms = `sms:${phone}?body=${encodeURIComponent(message)}`;
    const whatsapp = `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
    const mailto = `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(`${camLabel(enrollment.academy_name)} Player Enrollment`)}&body=${encodeURIComponent(message)}`;
    host.innerHTML = `<div class="cam-share-box"><strong>Enrollment link ready for ${esc(parentName(review))}</strong><div class="cam-share-url">${esc(enrollment.enrollment_url)}</div><div class="cam-share-actions"><button data-enroll-share="sms">Text Message</button><button data-enroll-share="whatsapp">WhatsApp</button>${email && email !== '—' ? '<button data-enroll-share="email">Email</button>' : ''}<button data-enroll-share="copy">Copy Link</button></div><small style="display:block;margin-top:9px;color:#647d70">Enrollment status: ${esc(enrollment.status || 'created')}</small></div>`;
    $('[data-enroll-share="sms"]', host)?.addEventListener('click', async () => { await markSent(enrollment.id, 'sms'); location.href = sms; });
    $('[data-enroll-share="whatsapp"]', host)?.addEventListener('click', async () => { await markSent(enrollment.id, 'whatsapp'); window.open(whatsapp, '_blank', 'noopener'); });
    $('[data-enroll-share="email"]', host)?.addEventListener('click', async () => { await markSent(enrollment.id, 'email'); location.href = mailto; });
    $('[data-enroll-share="copy"]', host)?.addEventListener('click', async () => { await navigator.clipboard.writeText(enrollment.enrollment_url); notify('Enrollment link copied.'); });
  }

  async function createEnrollmentLink(review, button) {
    const appId = applicationId(review);
    if (!appId) return notify('Could not determine the registration application.');
    if (!confirm('Approve this registration and create the secure parent enrollment link?')) return;
    button.disabled = true;
    button.textContent = 'Approving…';
    try {
      const enrollment = await requestJson(`/api/cam/enrollments/from-registration/${appId}`, {method:'POST', body:'{}'});
      notify('Registration approved. Enrollment link is ready.');
      $$('.cam-review-actions button', review).forEach(btn => btn.disabled = true);
      button.textContent = 'Approved';
      showEnrollmentShare(review, enrollment);
    } catch (err) {
      notify(err.message);
      button.disabled = false;
      button.textContent = 'Approve & Send Enrollment Link';
    }
  }

  async function addApprovedEnrollmentControls(review) {
    if (review.dataset.enrollmentApprovedControls === '1') return;
    review.dataset.enrollmentApprovedControls = '1';
    const appId = applicationId(review);
    if (!appId) return;
    const actions = $('.cam-review-actions', review);
    if (!actions) return;
    const button = document.createElement('button');
    button.className = 'primary';
    button.type = 'button';
    button.textContent = 'Generate Enrollment Link';
    actions.appendChild(button);
    try {
      const existing = await requestJson(`/api/cam/enrollments/by-application/${appId}`);
      button.textContent = `Generate New Enrollment Link · ${existing.status || 'created'}`;
    } catch {}
    button.addEventListener('click', () => createEnrollmentLink(review, button));
  }

  function patchReview(review) {
    if (!review || review.dataset.enrollmentSlice2aPatched === '1') return;
    review.dataset.enrollmentSlice2aPatched = '1';

    const requestButton = $('[data-review-action="needs_information"]', review);
    requestButton?.remove();
    $('.cam-review-note', review)?.remove();

    const approve = $('[data-review-action="approve"]', review);
    if (approve) {
      const replacement = approve.cloneNode(true);
      replacement.removeAttribute('data-review-action');
      replacement.id = 'approveAndSendEnrollmentLink';
      replacement.textContent = 'Approve & Send Enrollment Link';
      approve.replaceWith(replacement);
      replacement.addEventListener('click', () => createEnrollmentLink(review, replacement));
    }

    const statusText = $('.cam-registration-head p', review)?.textContent || '';
    if (/Status:\s*Approved/i.test(statusText)) addApprovedEnrollmentControls(review);
  }

  async function loadBranding() {
    try {
      const data = await requestJson('/api/cam/registration/branding');
      camName = data?.academy_name || 'Academy';
    } catch {}
  }

  function apply() {
    document.querySelectorAll('.cam-registration-review').forEach(patchReview);
  }

  loadBranding();
  document.addEventListener('DOMContentLoaded', apply);
  new MutationObserver(apply).observe(document.documentElement, {childList:true, subtree:true});
  apply();
})();
