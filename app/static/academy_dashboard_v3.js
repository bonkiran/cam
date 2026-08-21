(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  let scheduled = false;
  let rendering = false;
  let lastData = null;
  let weatherCache = null;
  let weatherCacheAt = 0;

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

  function money(cents) {
    return new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:0}).format(Number(cents || 0) / 100);
  }

  function fmtDate(value, options = {}) {
    if (!value) return '—';
    const date = /^\d{4}-\d{2}-\d{2}$/.test(String(value))
      ? new Date(`${value}T12:00:00`)
      : new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric', ...options});
  }

  function fmtDayDate(value) {
    if (!value) return 'Date unavailable';
    const date = new Date(`${String(value).slice(0,10)}T12:00:00`);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString(undefined, {weekday:'short', month:'short', day:'numeric', year:'numeric'});
  }

  function fmtTime(value) {
    if (!value) return 'Time TBD';
    const [hour, minute] = String(value).slice(0,5).split(':').map(Number);
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return String(value);
    const date = new Date();
    date.setHours(hour, minute, 0, 0);
    return date.toLocaleTimeString([], {hour:'numeric', minute:'2-digit'});
  }

  function sessionTime(start, duration) {
    if (!start) return 'Time TBD';
    const [hour, minute] = String(start).slice(0,5).split(':').map(Number);
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return fmtTime(start);
    const startDate = new Date();
    startDate.setHours(hour, minute, 0, 0);
    const endDate = new Date(startDate.getTime() + Number(duration || 0) * 60000);
    return `${startDate.toLocaleTimeString([], {hour:'numeric', minute:'2-digit'})} – ${endDate.toLocaleTimeString([], {hour:'numeric', minute:'2-digit'})}`;
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {cache:'no-store', ...options, headers:{'Content-Type':'application/json', ...(options.headers || {})}});
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    return data;
  }

  function go(tab) {
    location.hash = tab === 'overview' ? 'academy' : `academy?tab=${encodeURIComponent(tab)}`;
  }

  function notify(message) {
    if (typeof window.toast === 'function') window.toast(message);
    else console.log(message);
  }

  function countryCode(value) {
    const raw = String(value || '').trim().toLowerCase();
    const aliases = {'united states':'US','united states of america':'US','usa':'US','us':'US','canada':'CA','ca':'CA','india':'IN','in':'IN','united kingdom':'GB','uk':'GB','gb':'GB'};
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

  async function geocodeAcademy(academy) {
    const city = String(academy?.city || '').trim();
    const state = String(academy?.state || '').trim();
    const postal = String(academy?.postal_code || '').trim();
    const terms = [];
    if (city && state) terms.push(`${city}, ${state}`);
    if (city) terms.push(city);
    if (postal) terms.push(postal);
    for (const term of [...new Set(terms)]) {
      const params = new URLSearchParams({name:term, count:'8', language:'en', format:'json'});
      const code = countryCode(academy?.country);
      if (code) params.set('countryCode', code);
      const data = await requestJson(`https://geocoding-api.open-meteo.com/v1/search?${params.toString()}`);
      const results = Array.isArray(data?.results) ? data.results : [];
      if (!results.length) continue;
      if (city) {
        const exact = results.find(item => String(item?.name || '').toLowerCase() === city.toLowerCase());
        if (exact) return exact;
      }
      return results[0];
    }
    return null;
  }

  async function loadWeather(academy) {
    const now = Date.now();
    if (weatherCache && now - weatherCacheAt < 10 * 60 * 1000) return weatherCache;
    try {
      const place = await geocodeAcademy(academy);
      if (!place) throw new Error('Location unavailable');
      const params = new URLSearchParams({
        latitude:String(place.latitude),
        longitude:String(place.longitude),
        current:'temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m',
        daily:'weather_code,temperature_2m_max,temperature_2m_min',
        temperature_unit:'fahrenheit',
        wind_speed_unit:'mph',
        timezone:'auto',
        forecast_days:'7',
      });
      const data = await requestJson(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);
      const daily = data?.daily || {};
      const days = (daily.time || []).map((date, index) => ({
        date,
        code: daily.weather_code?.[index],
        high: daily.temperature_2m_max?.[index],
        low: daily.temperature_2m_min?.[index],
      }));
      weatherCache = {
        ok:true,
        current:data?.current || {},
        days,
        location:[academy?.city || place.name, academy?.state || place.admin1].filter(Boolean).join(', '),
      };
    } catch (error) {
      console.warn('Dashboard weekly weather unavailable:', error);
      weatherCache = {ok:false, current:{}, days:[], location:[academy?.city, academy?.state].filter(Boolean).join(', ')};
    }
    weatherCacheAt = now;
    return weatherCache;
  }

  function weatherMarkup(weather) {
    if (!weather?.ok) {
      return `<section class="cam-v3-weather"><div class="cam-v3-weather-current"><div class="cam-v3-weather-icon">🌤️</div><div><strong>Weather unavailable</strong><span>${esc(weather?.location || 'Academy location')}</span><small>Live forecast will retry automatically.</small></div></div><div class="cam-v3-forecast-empty">7-day forecast temporarily unavailable.</div></section>`;
    }
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
    return `<section class="cam-v3-weather"><div class="cam-v3-weather-current"><div class="cam-v3-weather-icon">${weatherIcon(current.weather_code)}</div><div><strong>${Number.isFinite(Number(current.temperature_2m)) ? Math.round(Number(current.temperature_2m)) : '—'}°F</strong><span>${esc(weatherLabel(current.weather_code))}</span><small>${esc(weather.location || 'Academy')}${details.length ? ` · ${esc(details.join(' · '))}` : ''}</small></div></div><div class="cam-v3-forecast">${days}</div></section>`;
  }

  function programCountsMarkup(data) {
    const counts = data.program_counts || {buckets:{}, total_players:0};
    const buckets = ['Beginners','U11','U13','U14','U15'];
    const cards = buckets.map((name, index) => `<div class="cam-v3-program-chip tone-${index + 1}"><span>${esc(name)}</span><strong>${Number(counts.buckets?.[name] || 0)}</strong></div>`).join('');
    return `<article class="cam-v3-card cam-v3-player-counts"><div class="cam-v3-card-title"><span class="cam-v3-icon">👥</span><h2>Players in Programs</h2></div><div class="cam-v3-program-grid">${cards}<div class="cam-v3-total-players"><span>Total Players</span><strong>${Number(counts.total_players || 0)}</strong><small>Active academy directory</small></div></div></article>`;
  }

  function assignmentMarkup(player) {
    if (player.batch_id) {
      const status = player.batch_status === 'waitlisted' ? 'Waitlisted' : 'Assigned';
      return `<span class="cam-v3-assigned">${esc(status)} · ${esc(player.batch_name || 'Batch')}</span>`;
    }
    return `<button type="button" class="cam-v3-primary cam-v3-assign-batch" data-player-id="${Number(player.player_id)}">Assign Batch</button>`;
  }

  function newEnrollmentsMarkup(data) {
    const section = data.new_enrollments || {count:0, players:[]};
    const rows = (section.players || []).slice(0,4).map(player => `<div class="cam-v3-enrollment-row" data-player-id="${Number(player.player_id)}"><div><strong>${esc(player.player_name)}</strong><small>Enrollment complete</small></div><div><span>Enrolled ${esc(fmtDate(player.enrolled_date))}</span><small>${esc(player.parent_name || 'Parent / Guardian')}</small></div><div>${assignmentMarkup(player)}</div><div class="cam-v3-batch-editor"></div></div>`).join('');
    return `<article class="cam-v3-card cam-v3-new-enrollments"><div class="cam-v3-card-title"><span class="cam-v3-icon">👤+</span><h2>${esc(data.month_label)} - New Enrollment : ${Number(section.count || 0)}</h2></div>${rows || '<div class="cam-v3-empty">No completed enrollments this month.</div>'}</article>`;
  }

  function statusLabel(status) {
    const map = {created:'Created',sent:'Sent',opened:'Opened',in_progress:'In Progress',needs_information:'Needs Info',submitted:'Submitted',approved:'Approved',declined:'Declined',expired:'Expired',cancelled:'Cancelled'};
    return map[String(status || '')] || String(status || 'Created');
  }

  function statusTone(status) {
    if (['approved','submitted'].includes(status)) return 'good';
    if (['sent','opened'].includes(status)) return 'blue';
    if (['in_progress','needs_information','created'].includes(status)) return 'amber';
    if (['declined','expired','cancelled'].includes(status)) return 'bad';
    return 'neutral';
  }

  function trackerMarkup(data) {
    const tracker = data.registration_tracker || {rows:[]};
    const rows = (tracker.rows || []).map(row => {
      const activity = row.activity_at || row.sent_at;
      return `<tr><td>${esc(row.parent_name)}</td><td>${esc(row.sent_by)}</td><td><strong>${esc(activity ? new Date(activity).toLocaleString([], {month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'}) : 'Not sent')}</strong>${row.sent_at ? '<small>Link activity tracked</small>' : '<small>Link not sent yet</small>'}</td><td><span class="cam-v3-status ${statusTone(row.status)}">${esc(statusLabel(row.status))}</span></td><td>${esc(row.player_name)}</td><td><button type="button" class="cam-v3-table-action" data-open-registration="1">View</button></td></tr>`;
    }).join('');
    return `<article class="cam-v3-card cam-v3-tracker"><div class="cam-v3-card-title cam-v3-title-row"><span class="cam-v3-icon">➤</span><h2>${esc(data.month_label)} - Enrollment Links Sent : ${Number(tracker.links_sent_count || 0)} <i></i> Enrollment Tracker : ${Number(tracker.tracker_count || 0)}</h2></div><div class="cam-v3-table-wrap"><table><thead><tr><th>Parent</th><th>Sent By</th><th>Sent / Activity</th><th>Status</th><th>Player</th><th>Actions</th></tr></thead><tbody>${rows || '<tr><td colspan="6">No enrollment-link activity this month.</td></tr>'}</tbody></table></div></article>`;
  }

  function groupSessionRows(rows = []) {
    return rows.map(row => `<tr><td>${esc(row.batch_name || 'Group Session')}</td><td>${esc(row.coach_name || 'Coach not assigned')}</td><td>${esc(row.location || 'Location not set')}</td><td>${esc(sessionTime(row.start_time, row.duration_minutes))}</td></tr>`).join('');
  }

  function privateSessionRows(rows = []) {
    return rows.map(row => `<tr><td>${esc(row.player_name || 'Player')}</td><td>${esc(row.coach_name || 'Coach not assigned')}</td><td>${esc(row.location || 'Location not set')}</td><td>${esc(sessionTime(row.start_time, row.duration_minutes))}</td></tr>`).join('');
  }

  function sessionsMarkup(data) {
    const sessions = data.sessions || {group:[], private:[], count:0};
    return `<article class="cam-v3-card cam-v3-sessions"><div class="cam-v3-card-title"><span class="cam-v3-icon">🗓</span><h2>${esc(fmtDayDate(data.as_of))} Sessions : ${Number(sessions.count || 0)}</h2></div><div class="cam-v3-session-grid"><section><h3>Group Sessions · ${sessions.group?.length || 0}</h3><div class="cam-v3-table-wrap"><table><thead><tr><th>Batch</th><th>Coach</th><th>Venue</th><th>Time</th></tr></thead><tbody>${groupSessionRows(sessions.group) || '<tr><td colspan="4">No group sessions scheduled today.</td></tr>'}</tbody></table></div></section><section><h3>1 on 1 Sessions · ${sessions.private?.length || 0}</h3><div class="cam-v3-table-wrap"><table><thead><tr><th>Player</th><th>Coach</th><th>Venue</th><th>Time</th></tr></thead><tbody>${privateSessionRows(sessions.private) || '<tr><td colspan="4">No 1 on 1 sessions scheduled today.</td></tr>'}</tbody></table></div></section></div></article>`;
  }

  function moneyMetric(label, value, note, tone = '') {
    return `<div class="cam-v3-money-metric ${tone}"><span>${esc(label)}</span><strong>${esc(money(value))}</strong><small>${esc(note)}</small></div>`;
  }

  function financeMarkup(data) {
    const receipts = data.receipts || {};
    const payments = data.payments || {};
    return `<section class="cam-v3-finance-grid"><article class="cam-v3-card"><div class="cam-v3-card-title"><span class="cam-v3-icon">＄</span><h2>${esc(data.month_label)} - Academy Receipts</h2></div><div class="cam-v3-money-grid two">${moneyMetric('Group Session Fee Received', receipts.group_session_fee_received_cents, 'Collected this month', 'positive')}${moneyMetric('Group Session Fee Pending', receipts.group_session_fee_pending_cents, 'Pending payments', 'pending')}</div></article><article class="cam-v3-card"><div class="cam-v3-card-title"><span class="cam-v3-icon">▣</span><h2>${esc(data.month_label)} - Academy Payments</h2></div><div class="cam-v3-money-grid three">${moneyMetric('Coach Salary Payments', payments.coach_salary_payments_cents, 'Paid this month')}${moneyMetric('Facility Payments', payments.facility_payments_cents, 'Paid this month')}${moneyMetric('Academy Expenses', payments.academy_expenses_cents, 'This month')}</div></article></section>`;
  }

  function eventDateRange(start, end) {
    if (!start) return 'Date TBD';
    if (!end || end === start) return fmtDate(start, {weekday:'short'});
    return `${fmtDate(start, {weekday:'short'})} – ${fmtDate(end, {weekday:'short'})}`;
  }

  function matchEvents(rows = []) {
    return rows.map(row => `<div class="cam-v3-event-row"><span class="cam-v3-event-icon">🗓</span><div><strong>${esc(row.team_name || 'CAM')} vs ${esc(row.opponent || 'Opponent')}</strong><small>${esc(fmtDate(row.match_date, {weekday:'short'}))} · ${esc(fmtTime(row.start_time))}</small><small>${esc(row.venue || 'Location TBD')}</small></div></div>`).join('');
  }

  function programEvents(rows = []) {
    return rows.map(row => `<div class="cam-v3-event-row"><span class="cam-v3-event-icon purple">▦</span><div><strong>${esc(row.name || 'Program')}</strong><small>${esc(eventDateRange(row.start_date, row.end_date))} · ${esc(fmtTime(row.start_time))}</small><small>${esc(row.location || 'Location TBD')}</small></div></div>`).join('');
  }

  function tournamentEvents(rows = []) {
    return rows.map(row => `<div class="cam-v3-event-row"><span class="cam-v3-event-icon amber">🏆</span><div><strong>${esc(row.name || 'Tournament')}</strong><small>${esc(eventDateRange(row.start_date, row.end_date))} · All Day</small><small>${esc(row.location || 'Location TBD')}</small></div></div>`).join('');
  }

  function eventsMarkup(data) {
    const events = data.events || {};
    const column = (title, rows, type, tab) => `<section class="cam-v3-event-column"><div class="cam-v3-event-head"><h3>${esc(title)}</h3><button type="button" data-dashboard-tab="${esc(tab)}">View All →</button></div>${rows || '<div class="cam-v3-empty compact">No upcoming items.</div>'}</section>`;
    return `<article class="cam-v3-card cam-v3-events"><div class="cam-v3-card-title"><span class="cam-v3-icon">🗓</span><h2>${esc(data.month_label)} - Upcoming Events</h2></div><div class="cam-v3-events-grid">${column('Matches', matchEvents(events.matches), 'matches', 'teams')}${column('Camps / Programs', programEvents(events.programs), 'programs', 'programs')}${column('Tournaments', tournamentEvents(events.tournaments), 'tournaments', 'tournaments')}</div></article>`;
  }

  function attendanceMarkup(data) {
    const attendance = data.attendance || {batches:[], total_scheduled:0};
    const cards = (attendance.batches || []).map(row => `<div class="cam-v3-attendance-card"><span>${esc(row.batch)}</span><strong>Attended ${Number(row.attended || 0)} / ${Number(row.scheduled || 0)}</strong><div class="cam-v3-progress"><i style="width:${Math.max(0, Math.min(100, Number(row.attendance_percent || 0)))}%"></i></div><b>${Number(row.attendance_percent || 0).toFixed(0)}%</b></div>`).join('');
    const title = attendance.date ? `${fmtDayDate(attendance.date)}${attendance.latest_time ? ` · ${fmtTime(attendance.latest_time)}` : ''} – Session Attendance` : 'Session Attendance';
    return `<article class="cam-v3-card cam-v3-attendance"><div class="cam-v3-card-title cam-v3-title-between"><div><span class="cam-v3-icon">👥</span><h2>${esc(title)}</h2></div><div class="cam-v3-attendance-total">Total: ${Number(attendance.total_scheduled || 0)}</div></div><div class="cam-v3-attendance-grid">${cards || '<div class="cam-v3-empty">No group-session attendance recorded yet.</div>'}</div></article>`;
  }

  function dashboardMarkup(data, weather) {
    return `<div class="cam-dashboard-v3"><section class="cam-v3-hero"><div class="cam-v3-welcome"><span>ACADEMY DASHBOARD</span><h1>Welcome, ${esc(data.user?.display_name || 'Admin')}</h1><p>${esc(data.academy?.name || 'CAM Academy')} Operations Dashboard</p></div>${weatherMarkup(weather)}</section><section class="cam-v3-two-col">${programCountsMarkup(data)}${newEnrollmentsMarkup(data)}</section>${trackerMarkup(data)}${sessionsMarkup(data)}${financeMarkup(data)}${eventsMarkup(data)}${attendanceMarkup(data)}</div>`;
  }

  async function openBatchEditor(button) {
    const playerId = Number(button.dataset.playerId || 0);
    const row = button.closest('.cam-v3-enrollment-row');
    const editor = $('.cam-v3-batch-editor', row);
    const player = lastData?.new_enrollments?.players?.find(item => Number(item.player_id) === playerId);
    if (!editor || !player) return;
    editor.innerHTML = '<div class="cam-v3-editor-box">Loading active batches…</div>';
    try {
      const batches = await requestJson('/api/academy/batches');
      const activeBatches = (Array.isArray(batches) ? batches : []).filter(batch => String(batch.status || '') === 'active');
      const options = activeBatches.map(batch => {
        const activeCount = Number(batch.active_player_count || 0);
        const capacity = Number(batch.capacity || 0);
        const full = capacity > 0 && activeCount >= capacity;
        return `<option value="${Number(batch.id)}" ${full ? 'disabled' : ''}>${esc(batch.name || `Batch ${batch.id}`)}${capacity ? ` · ${activeCount}/${capacity}` : ''}${full ? ' · Full' : ''}</option>`;
      }).join('');
      const open = activeBatches.some(batch => Number(batch.capacity || 0) <= 0 || Number(batch.active_player_count || 0) < Number(batch.capacity || 0));
      editor.innerHTML = `<form class="cam-v3-editor-box cam-v3-batch-form"><label><span>Batch</span><select name="batch_id" required ${open ? '' : 'disabled'}><option value="">Select batch</option>${options}</select></label><label><span>Start date</span><input name="joined_on" type="date" value="${esc(player.enrolled_date || lastData.as_of)}" required></label><div class="cam-v3-editor-actions"><small class="cam-v3-editor-status">${open ? '' : 'All active batches are full.'}</small><button type="button" class="cam-v3-secondary cam-v3-editor-cancel">Cancel</button><button type="submit" class="cam-v3-primary" ${open ? '' : 'disabled'}>Confirm Assignment</button></div></form>`;
      $('.cam-v3-editor-cancel', editor).onclick = () => { editor.innerHTML = ''; };
      const form = $('.cam-v3-batch-form', editor);
      form.onsubmit = async event => {
        event.preventDefault();
        const values = new FormData(form);
        const batchId = Number(values.get('batch_id') || 0);
        const joinedOn = String(values.get('joined_on') || '');
        const submit = $('button[type="submit"]', form);
        const status = $('.cam-v3-editor-status', form);
        if (!batchId) return;
        submit.disabled = true;
        status.textContent = 'Assigning…';
        try {
          await requestJson(`/api/academy/batches/${batchId}/players`, {method:'POST', body:JSON.stringify({player_id:playerId, waitlist_if_full:false, joined_on:joinedOn})});
          notify(`${player.player_name} assigned to batch.`);
          await render(true);
        } catch (error) {
          status.textContent = error.message || 'Assignment failed.';
          submit.disabled = false;
        }
      };
    } catch (error) {
      editor.innerHTML = `<div class="cam-v3-editor-box">${esc(error.message || 'Could not load batches.')}</div>`;
    }
  }

  function wire(root) {
    $$('.cam-v3-assign-batch', root).forEach(button => { button.onclick = () => openBatchEditor(button); });
    $$('[data-open-registration]', root).forEach(button => { button.onclick = () => { location.hash = 'registration'; }; });
    $$('[data-dashboard-tab]', root).forEach(button => { button.onclick = () => go(button.dataset.dashboardTab); });
  }

  function suppressLegacy(content) {
    content.dataset.dashboardV3 = '1';
    [...content.children].forEach(child => {
      if (!child.classList.contains('cam-dashboard-v3')) child.classList.add('cam-v3-legacy-sibling');
    });
  }

  async function render(force = false) {
    if (!active() || rendering) return;
    const content = $('#academyWorkspace .academy-content');
    if (!content) return;
    if (!force && content.dataset.dashboardV3 === '1' && $('.cam-dashboard-v3', content)) {
      suppressLegacy(content);
      return;
    }
    rendering = true;
    document.body.classList.add('cam-academy-dashboard-v3-mode');
    try {
      const data = await requestJson('/api/academy/dashboard/v3');
      const weather = await loadWeather(data.academy || {});
      if (!active() || !content.isConnected) return;
      lastData = data;
      content.innerHTML = dashboardMarkup(data, weather);
      suppressLegacy(content);
      wire(content);
    } catch (error) {
      content.innerHTML = `<div class="warning">Dashboard could not load: ${esc(error.message)}</div>`;
      content.dataset.dashboardV3 = '1';
    } finally {
      rendering = false;
    }
  }

  function apply() {
    scheduled = false;
    if (!active()) {
      document.body.classList.remove('cam-academy-dashboard-v3-mode');
      return;
    }
    document.body.classList.add('cam-academy-dashboard-v3-mode');
    render(false);
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(apply);
  }

  window.addEventListener('hashchange', () => {
    if (!active()) document.body.classList.remove('cam-academy-dashboard-v3-mode');
    schedule();
  });
  window.addEventListener('academy-payments-updated', () => render(true));
  window.addEventListener('academy-enrollment-completed', () => render(true));
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(() => {
    if (!active()) return;
    const content = $('#academyWorkspace .academy-content');
    if (content?.dataset.dashboardV3 === '1') suppressLegacy(content);
    else schedule();
  }).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
