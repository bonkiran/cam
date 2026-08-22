(() => {
  const ROUTE = 'integrations';
  const rootSelector = '[data-cam-payment-integrations]';
  let rendering = false;

  function activeRoute() {
    return (location.hash.replace(/^#/, '').split('?')[0] || 'dashboard').trim();
  }

  function esc(value = '') {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[char]));
  }

  function messageFromError(data, fallback) {
    const detail = data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object') return detail.message || detail.code || fallback;
    return fallback;
  }

  async function providerApi(url, options = {}) {
    const response = await fetch(url, {
      cache: 'no-store',
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    });
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(messageFromError(data, `Request failed (${response.status})`));
    return data;
  }

  function statusLabel(item) {
    if (item.selected) return 'Selected';
    const connection = item.connection || {};
    if (connection.status === 'connected') return 'Connected';
    if (!item.configured) return 'Not configured';
    if (connection.status === 'error') return 'Connection error';
    return 'Ready to test';
  }

  function providerCard(item) {
    const provider = String(item.provider || '').toLowerCase();
    const connected = item.connection?.status === 'connected';
    const selected = !!item.selected;
    const configured = !!item.configured;
    const environment = item.environment || 'sandbox';
    const capabilities = (item.capabilities || []).filter(capability => capability !== 'sandbox');
    const setupHint = provider === 'stripe'
      ? 'Render variables: CAM_STRIPE_SECRET_KEY + CAM_STRIPE_PUBLISHABLE_KEY'
      : 'Render variables: CAM_SQUARE_ACCESS_TOKEN + CAM_SQUARE_APPLICATION_ID + CAM_SQUARE_LOCATION_ID + CAM_SQUARE_ENVIRONMENT=sandbox';
    const safeClient = item.client_config || {};
    const clientMarker = provider === 'stripe'
      ? (safeClient.publishable_key ? `${String(safeClient.publishable_key).slice(0, 8)}…` : '—')
      : (safeClient.application_id ? `${String(safeClient.application_id).slice(0, 12)}…` : '—');

    return `<article class="panel cam-provider-card" data-provider="${esc(provider)}">
      <div class="cam-provider-card-head">
        <div>
          <span class="cam-provider-kicker">${esc(environment.toUpperCase())}</span>
          <h2>${esc(item.display_name || provider)}</h2>
          <p>${provider === 'stripe' ? 'Stripe Elements + SetupIntent for save-now / charge-later.' : 'Square Web Payments SDK + Cards API for card-on-file.'}</p>
        </div>
        <span class="cam-provider-status ${selected ? 'selected' : connected ? 'connected' : configured ? 'ready' : 'off'}">${esc(statusLabel(item))}</span>
      </div>
      <div class="cam-provider-meta">
        <div><span>Configured</span><strong>${configured ? 'Yes' : 'No'}</strong></div>
        <div><span>Client-safe key</span><strong>${esc(clientMarker)}</strong></div>
        <div><span>Merchant</span><strong>${esc(item.connection?.provider_merchant_id || '—')}</strong></div>
        <div><span>Location</span><strong>${esc(item.connection?.provider_location_id || '—')}</strong></div>
      </div>
      <div class="cam-provider-capabilities">${capabilities.map(cap => `<span>${esc(cap.replaceAll('_', ' '))}</span>`).join('')}</div>
      <p class="cam-provider-hint">${esc(setupHint)}</p>
      <div class="cam-provider-actions">
        <button type="button" class="secondary" data-provider-test="${esc(provider)}" ${configured ? '' : 'disabled'}>Test Connection</button>
        <button type="button" class="primary" data-provider-select="${esc(provider)}" ${connected && !selected ? '' : 'disabled'}>${selected ? 'Selected' : 'Use This Provider'}</button>
      </div>
      <p class="cam-provider-result" data-provider-result="${esc(provider)}"></p>
    </article>`;
  }

  async function loadProviders(host) {
    const grid = host.querySelector('#camPaymentProviderGrid');
    const note = host.querySelector('#camProviderArchitectureNote');
    try {
      const data = await providerApi('/api/cam/payment-providers');
      const providers = Array.isArray(data?.providers) ? data.providers : [];
      grid.innerHTML = providers.map(providerCard).join('') || '<div class="warning">No payment providers are available.</div>';
      if (note) note.textContent = data?.architecture === 'provider_neutral'
        ? 'CAM Finance remains provider-neutral. Secrets stay outside the CAM database.'
        : 'Payment provider status loaded.';
      wireProviderActions(host);
    } catch (error) {
      grid.innerHTML = `<div class="warning">Payment providers could not load: ${esc(error.message)}</div>`;
    }
  }

  function setResult(host, provider, message, state = '') {
    const result = host.querySelector(`[data-provider-result="${provider}"]`);
    if (!result) return;
    result.textContent = message;
    result.dataset.state = state;
  }

  function wireProviderActions(host) {
    host.querySelectorAll('[data-provider-test]').forEach(button => {
      button.onclick = async () => {
        const provider = button.dataset.providerTest;
        button.disabled = true;
        button.textContent = 'Testing…';
        setResult(host, provider, 'Connecting securely to the provider sandbox…');
        try {
          const data = await providerApi(`/api/cam/payment-providers/${provider}/test-connection`, {method: 'POST', body: '{}'});
          setResult(host, provider, `${data.provider === 'stripe' ? 'Stripe' : 'Square'} sandbox connection successful.`, 'success');
          await loadProviders(host);
        } catch (error) {
          setResult(host, provider, `Connection failed: ${error.message}`, 'error');
          button.disabled = false;
          button.textContent = 'Test Connection';
        }
      };
    });

    host.querySelectorAll('[data-provider-select]').forEach(button => {
      button.onclick = async () => {
        const provider = button.dataset.providerSelect;
        button.disabled = true;
        button.textContent = 'Selecting…';
        try {
          await providerApi('/api/cam/payment-providers/select', {
            method: 'POST',
            body: JSON.stringify({provider}),
          });
          setResult(host, provider, `${provider === 'stripe' ? 'Stripe' : 'Square'} is now the selected CAM payment provider.`, 'success');
          await loadProviders(host);
        } catch (error) {
          setResult(host, provider, `Selection failed: ${error.message}`, 'error');
          button.disabled = false;
          button.textContent = 'Use This Provider';
        }
      };
    });
  }

  function pageMarkup() {
    const content = `${typeof pageHead === 'function' ? pageHead('Integrations', 'Connect external services without coupling CAM business logic to one vendor.') : '<section class="page-head"><div><h1>Integrations</h1><p>Connect external services securely.</p></div></section>'}
      <section data-cam-payment-integrations>
        <article class="panel cam-provider-intro">
          <div>
            <span class="cam-provider-kicker">SLICE 2C · PAYMENT PROVIDERS</span>
            <h2>Stripe + Square compatibility</h2>
            <p id="camProviderArchitectureNote">Loading provider configuration…</p>
          </div>
          <span class="cam-provider-architecture-badge">PROVIDER NEUTRAL</span>
        </article>
        <section class="cam-provider-grid" id="camPaymentProviderGrid">
          <article class="panel"><div class="empty"><strong>Loading payment providers…</strong></div></article>
        </section>
        <article class="panel cam-provider-security-note">
          <strong>Security boundary</strong>
          <span>CAM never stores full card numbers or CVC/CVV. Secret API credentials stay in Render environment variables or future per-academy OAuth/secret storage.</span>
        </article>
      </section>`;
    return content;
  }

  async function renderIntegrations() {
    if (activeRoute() !== ROUTE || rendering) return;
    if (document.querySelector(rootSelector)) return;
    rendering = true;
    try {
      const app = document.querySelector('#app');
      if (!app) return;
      if (typeof shell === 'function') {
        app.innerHTML = shell(pageMarkup(), ROUTE);
        if (typeof wireShell === 'function') wireShell(ROUTE);
      } else {
        app.innerHTML = pageMarkup();
      }
      const host = document.querySelector(rootSelector);
      if (host) await loadProviders(host);
    } finally {
      rendering = false;
    }
  }

  function schedule() {
    window.setTimeout(renderIntegrations, 0);
  }

  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(() => {
    if (activeRoute() === ROUTE && !document.querySelector(rootSelector)) schedule();
  }).observe(document.documentElement, {childList: true, subtree: true});
  schedule();
})();
