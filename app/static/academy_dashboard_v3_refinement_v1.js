(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  let scheduled = false;
  let weatherCache = null;
  let weatherCacheAt = 0;
  let originalBrandHtml = null;

  function route() {
    const raw = location.hash.replace(/^#/, '');
    const [page, query = ''] = raw.split('?');
    return {page: page || 'dashboard', tab: new URLSearchParams(query).get('tab') || 'overview'};
  }

  function active() {
    const r = route();
    return r.page === 'academy' && r.tab === 'overview';
  }

  function esc(value = '') {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  async function internalJson(url, options = {}) {
    const response = await fetch(url, {
      cache: 'no-store',
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    });
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    return data;
  }

  // External weather calls intentionally use a plain GET with no custom JSON
  // headers. Adding Content-Type to Open-Meteo GETs triggers a browser CORS
  // preflight in some environments and was the reason the v3 weather card
  // could fall back to "Weather unavailable" while the old dashboard worked.
  async function externalJson(url) {
    const response = await fetch(url, {cache: 'no-store'});
    if (!response.ok) throw new Error(`Weather request failed (${response.status})`);
    return response.json();
  }

  function countryCode(value) {
    const raw = String(value || '').trim().toLowerCase();
    const aliases = {
      'united states':'US','united states of america':'US','usa':'US','us':'US',
      'canada':'CA','ca':'CA','india':'IN','in':'IN','united kingdom':'GB','uk':'GB','gb':'GB'
    };
    return aliases[raw] || (raw.length === 2 ? raw.toUpperCase() : '');
  }

  function weatherLabel(code) {
    const labels = {0:'Clear sky',1:'Mainly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',48:'Rime fog',51:'Light drizzle',53:'Drizzle',55:'Heavy drizzle',61:'Light rain',63:'Rain',65:'Heavy rain',71:'Light snow',73:'Snow',75:'Heavy snow',80:'Rain showers',81:'Rain showers',82:'Heavy showers',95:'Thunderstorms',96:'Storms with hail',99:'Severe storms'};
    return labels[Number(code)] || 'Current conditions';
  }

  function weatherIcon(code) {
    const n = Number(code);
    if (n === 0) return '☀️';
    if ([1,2].includes(n)) return '🌤️';
    if (n === 3) return '☁️';
    if ([45,48].includes(n)) return '🌫️';
    if ([51,53,55,61,63,65,80,81,82].includes(n)) return '🌧️';
    if ([71,73,75].includes(n)) return '🌨️';
    if ([95,96,99].includes(n)) return '⛈️';
    return '🌤️';
  }

  async function profile() {
    const data = await internalJson('/api/academy/profile');
    return data?.profile || data || {};
  }

  async function resolveLocation(p) {
    const city = String(p?.city || '').trim();
    const state = String(p?.state || '').trim();
    const postal = String(p?.postal_code || '').trim();
    const code = countryCode(p?.country);
    const terms = [];
    if (postal) terms.push(postal);
    if (city) terms.push(city);
    if (city && state) terms.push(`${city} ${state}`);
    for (const term of [...new Set(terms)]) {
      const params = new URLSearchParams({name: term, count: '10', language: 'en', format: 'json'});
      if (code) params.set('countryCode', code);
      const data = await externalJson(`https://geocoding-api.open-meteo.com/v1/search?${params.toString()}`);
      const results = Array.isArray(data?.results) ? data.results : [];
      if (!results.length) continue;
      if (city) {
        const exact = results.find(item => String(item?.name || '').trim().toLowerCase() === city.toLowerCase());
        if (exact) return exact;
      }
      return results[0];
    }
    return null;
  }

  async function loadWeather() {
    const now = Date.now();
    if (weatherCache && now - weatherCacheAt < 10 * 60 * 1000) return weatherCache;
    const p = await profile();
    const place = await resolveLocation(p);
    if (!place) throw new Error('Academy location could not be resolved');
    const params = new URLSearchParams({
      latitude: String(place.latitude),
      longitude: String(place.longitude),
      current: 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m',
      daily: 'weather_code,temperature_2m_max,temperature_2m_min',
      temperature_unit: 'fahrenheit',
      wind_speed_unit: 'mph',
      timezone: 'auto',
      forecast_days: '7',
    });
    const data = await externalJson(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);
    const daily = data?.daily || {};
    weatherCache = {
      ok: true,
      current: data?.current || {},
      days: (daily.time || []).map((date, index) => ({
        date,
        code: daily.weather_code?.[index],
        high: daily.temperature_2m_max?.[index],
        low: daily.temperature_2m_min?.[index],
      })),
      location: [p?.city || place.name, p?.state || place.admin1].filter(Boolean).join(', '),
    };
    weatherCacheAt = now;
    return weatherCache;
  }

  function renderWeather(weather) {
    const host = $('.cam-v3-weather');
    if (!host || !weather?.ok) return;
    const current = weather.current || {};
    const details = [];
    if (current.relative_humidity_2m !== undefined) details.push(`Humidity ${Math.round(Number(current.relative_humidity_2m))}%`);
    if (current.wind_speed_10m !== undefined) details.push(`Wind ${Math.round(Number(current.wind_speed_10m))} mph`);
    const days = (weather.days || []).map(day => {
      const date = new Date(`${day.date}T12:00:00`);
      const dow = date.toLocaleDateString(undefined, {weekday:'short'}).toUpperCase();
      const md = date.toLocaleDateString(undefined, {month:'short', day:'numeric'});
      return `<div class="cam-v3-forecast-day"><b>${esc(dow)}</b><small>${esc(md)}</small><span>${weatherIcon(day.code)}</span><strong>${Number.isFinite(Number(day.high)) ? Math.round(Number(day.high)) : '—'}°</strong><em>${Number.isFinite(Number(day.low)) ? Math.round(Number(day.low)) : '—'}°</em></div>`;
    }).join('');
    host.innerHTML = `<div class="cam-v3-weather-current"><div class="cam-v3-weather-icon">${weatherIcon(current.weather_code)}</div><div><strong>${Number.isFinite(Number(current.temperature_2m)) ? Math.round(Number(current.temperature_2m)) : '—'}°F</strong><span>${esc(weatherLabel(current.weather_code))}</span><small>${esc(weather.location || 'Academy')}${details.length ? ` · ${esc(details.join(' · '))}` : ''}</small></div></div><div class="cam-v3-forecast">${days}</div>`;
  }

  async function refreshWeather() {
    if (!active() || !$('.cam-v3-weather')) return;
    try {
      renderWeather(await loadWeather());
    } catch (error) {
      console.warn('C17 dashboard weather unavailable:', error);
    }
  }

  function applyBranding() {
    const brand = $('.sidebar .brand');
    if (active()) {
      if (brand) {
        if (originalBrandHtml === null) originalBrandHtml = brand.innerHTML;
        if (!brand.classList.contains('cam-c17-sidebar-brand')) {
          brand.classList.add('cam-c17-sidebar-brand');
          brand.innerHTML = `<img src="/static/c17_cricket_academy_logo.png" alt="C17 Cricket Academy logo"><strong>C17 Cricket Academy</strong>`;
        }
      }
      const kicker = $('.cam-v3-welcome > span');
      const subtitle = $('.cam-v3-welcome > p');
      if (kicker) kicker.textContent = 'C17 CRICKET ACADEMY';
      if (subtitle) subtitle.textContent = 'C17 Cricket Academy Operations Dashboard';
    } else if (brand && originalBrandHtml !== null && brand.classList.contains('cam-c17-sidebar-brand')) {
      brand.classList.remove('cam-c17-sidebar-brand');
      brand.innerHTML = originalBrandHtml;
    }
  }

  function localMonth(value) {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : {year:d.getFullYear(), month:d.getMonth()};
  }

  function formatActivity(value) {
    if (!value) return 'Not sent';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleString([], {month:'short', day:'numeric', year:'numeric', hour:'numeric', minute:'2-digit'});
  }

  function statusLabel(status, completed) {
    if (completed) return 'Completed';
    const map = {created:'Created',sent:'Sent',opened:'Opened',in_progress:'In Progress',needs_information:'Needs Info',submitted:'Submitted',approved:'Approved',declined:'Declined',expired:'Expired',cancelled:'Cancelled'};
    return map[String(status || '')] || String(status || 'Created');
  }

  function statusTone(status, completed) {
    if (completed || ['approved','submitted'].includes(status)) return 'good';
    if (['sent','opened'].includes(status)) return 'blue';
    if (['in_progress','needs_information','created'].includes(status)) return 'amber';
    if (['declined','expired','cancelled'].includes(status)) return 'bad';
    return 'neutral';
  }

  function trackerPlayerName(item) {
    return [item.player_first_name, item.player_last_name].filter(Boolean).join(' ') || 'Pending player details';
  }

  function trackerParentName(item) {
    return [item.parent_first_name, item.parent_last_name].filter(Boolean).join(' ') || 'Parent / Guardian';
  }

  function trackerAction(item, completed) {
    const status = String(item.status || 'created');
    if (!completed && ['created','sent','expired'].includes(status) && !item.submitted_at) {
      return `<button type="button" class="cam-v3-table-action" data-c17-resend="${Number(item.id)}">Resend</button>`;
    }
    return `<button type="button" class="cam-v3-table-action" data-c17-view-registration="1">View</button>`;
  }

  async function renderEnrollmentPrototype() {
    if (!active()) return;
    const old = $('.cam-v3-tracker');
    const existing = $('.cam-v3-enrollment-prototype');
    if (!old && !existing) return;
    try {
      const invites = await internalJson('/api/academy/registration/invites');
      const list = Array.isArray(invites) ? invites : [];
      const now = new Date();
      const completedNames = new Set($$('.cam-v3-new-enrollments .cam-v3-enrollment-row strong').map(el => el.textContent.trim().toLowerCase()));
      const monthRows = list.filter(item => {
        const stamp = item.last_activity_at || item.sent_at || item.created_at;
        const m = localMonth(stamp);
        return m && m.year === now.getFullYear() && m.month === now.getMonth();
      });
      const linksSent = list.filter(item => {
        const m = localMonth(item.sent_at);
        return m && m.year === now.getFullYear() && m.month === now.getMonth();
      }).length;
      const monthLabel = now.toLocaleDateString(undefined, {month:'long', year:'numeric'});
      const rows = monthRows.slice(0, 8).map(item => {
        const player = trackerPlayerName(item);
        const completed = completedNames.has(player.toLowerCase());
        const activity = item.last_activity_at || item.sent_at || item.created_at;
        return `<tr><td>${esc(trackerParentName(item))}</td><td>${esc(item.sent_by_name || 'Academy Staff')}</td><td><strong>${esc(formatActivity(activity))}</strong><small>${item.sent_at ? `Sent ${esc(formatActivity(item.sent_at))}` : 'Link not sent yet'}</small></td><td><span class="cam-v3-status ${statusTone(item.status, completed)}">${esc(statusLabel(item.status, completed))}</span></td><td>${esc(player)}</td><td>${trackerAction(item, completed)}</td></tr>`;
      }).join('');
      const section = document.createElement('section');
      section.className = 'cam-v3-enrollment-prototype';
      section.innerHTML = `<article class="cam-v3-card cam-v3-links-sent"><div class="cam-v3-card-title"><span class="cam-v3-icon">➤</span><h2>${esc(monthLabel)} -<br>Enrollment Links Sent : ${linksSent}</h2></div><strong class="cam-v3-links-count">${linksSent}</strong><span class="cam-v3-links-note">Links sent this month</span></article><article class="cam-v3-card cam-v3-tracker-prototype"><div class="cam-v3-card-title"><h2>Enrollment Tracker : ${monthRows.length}</h2></div><div class="cam-v3-table-wrap"><table><thead><tr><th>Parent</th><th>Sent By</th><th>Sent / Activity</th><th>Status</th><th>Player</th><th>Actions</th></tr></thead><tbody>${rows || '<tr><td colspan="6">No enrollment-link activity this month.</td></tr>'}</tbody></table></div><button type="button" class="cam-v3-view-all-links" data-c17-view-registration="1">View all enrollment links →</button></article>`;
      if (old) old.replaceWith(section);
      else existing.replaceWith(section);
      wireEnrollment(section);
    } catch (error) {
      console.warn('C17 enrollment tracker refinement unavailable:', error);
    }
  }

  function wireEnrollment(root) {
    $$('[data-c17-view-registration]', root).forEach(button => {
      button.onclick = () => { location.hash = 'academy?tab=registration'; };
    });
    $$('[data-c17-resend]', root).forEach(button => {
      button.onclick = async () => {
        button.disabled = true;
        try {
          await internalJson(`/api/academy/registration/invites/${button.dataset.c17Resend}/resend`, {method:'POST', body:'{}'});
          if (typeof window.toast === 'function') window.toast('Registration link regenerated.');
          await renderEnrollmentPrototype();
        } catch (error) {
          if (typeof window.toast === 'function') window.toast(error.message || 'Could not resend registration link.');
          button.disabled = false;
        }
      };
    });
  }

  function reorderRows() {
    if (!active()) return;
    const root = $('.cam-dashboard-v3');
    if (!root) return;
    const events = $('.cam-v3-events', root);
    const attendance = $('.cam-v3-attendance', root);
    const finance = $('.cam-v3-finance-grid', root);
    if (finance) finance.classList.add('cam-v3-finance-stack');
    if (events && finance) root.insertBefore(events, finance);
    if (attendance && finance) root.insertBefore(attendance, finance);
  }

  async function apply() {
    scheduled = false;
    applyBranding();
    if (!active()) return;
    const root = $('.cam-dashboard-v3');
    if (!root) return;
    reorderRows();
    await Promise.allSettled([refreshWeather(), renderEnrollmentPrototype()]);
    applyBranding();
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(apply, 40);
  }

  window.addEventListener('hashchange', schedule);
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(() => {
    if (active() && $('.cam-dashboard-v3')) schedule();
  }).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
