(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  let rendering = false;
  let scheduled = false;
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
    return r.page === 'cam' && r.tab === 'overview';
  }

  function esc(value = '') {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function money(cents) {
    return new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:0}).format(Number(cents || 0) / 100);
  }

  function localDate(value) {
    if (!value) return null;
    const raw = String(value);
    const date = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? new Date(`${raw}T12:00:00`) : new Date(raw);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function fmtDate(value, options = {}) {
    const date = localDate(value);
    if (!date) return value || '—';
    return date.toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric', ...options});
  }

  function fmtDayDate(value) {
    const date = localDate(value);
    if (!date) return value || 'Date unavailable';
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
    const a = new Date(); a.setHours(hour, minute, 0, 0);
    const b = new Date(a.getTime() + Number(duration || 0) * 60000);
    return `${a.toLocaleTimeString([], {hour:'numeric', minute:'2-digit'})} – ${b.toLocaleTimeString([], {hour:'numeric', minute:'2-digit'})}`;
  }

  async function requestJson(url, options = {}) {
    const headers = {...(options.headers || {})};
    if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    const response = await fetch(url, {cache:'no-store', ...options, headers});
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    return data;
  }

  function go(tab) {
    location.hash = tab === 'overview' ? 'cam' : `cam?tab=${encodeURIComponent(tab)}`;
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
    const code = countryCode(academy?.country);
    const terms = [city, postal, city && state ? `${city} ${state}` : ''].filter(Boolean);
    for (const term of [...new Set(terms)]) {
      const params = new URLSearchParams({name:term, count:'10', language:'en', format:'json'});
      if (code) params.set('countryCode', code);
      const data = await requestJson(`https://geocoding-api.open-meteo.com/v1/search?${params.toString()}`);
      const results = Array.isArray(data?.results) ? data.results : [];
      if (!results.length) continue;
      if (city) {
        const normalizedCity = city.toLowerCase().replace(/,.*$/, '').trim();
        const stateUpper = state.toUpperCase();
        const exact = results.find(item => {
          const itemCity = String(item?.name || '').toLowerCase();
          const admin = String(item?.admin1 || '').toUpperCase();
          return itemCity === normalizedCity && (!stateUpper || admin.includes(stateUpper) || String(item?.admin1 || '').toLowerCase().includes(state.toLowerCase()));
        });
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
      if (!place) throw new Error('Academy location could not be resolved');
      const params = new URLSearchParams({
        latitude:String(place.latitude), longitude:String(place.longitude),
        current:'temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m',
        daily:'weather_code,temperature_2m_max,temperature_2m_min',
        temperature_unit:'fahrenheit', wind_speed_unit:'mph', timezone:'auto', forecast_days:'7'
      });
      const data = await requestJson(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);
      const daily = data?.daily || {};
      weatherCache = {
        ok:true,
        current:data?.current || {},
        days:(daily.time || []).map((date, i) => ({date, code:daily.weather_code?.[i], high:daily.temperature_2m_max?.[i], low:daily.temperature_2m_min?.[i]})),
        location:[academy?.city || place.name, academy?.state || place.admin1].filter(Boolean).join(', ')
      };
    } catch (error) {
      console.warn('C17 dashboard weather unavailable:', error);
      weatherCache = {ok:false, current:{}, days:[], location:[academy?.city, academy?.state].filter(Boolean).join(', ')};
    }
    weatherCacheAt = now;
    return weatherCache;
  }

  function weatherMarkup(weather) {
    if (!weather?.ok) {
      return `<section class="c17-weather"><div class="c17-weather-now"><div class="c17-weather-icon">🌤️</div><div><strong>Weather temporarily unavailable</strong><span>${esc(weather?.location || 'Academy location')}</span><small>Live forecast will retry automatically.</small></div></div><div class="c17-forecast-empty">7-day forecast temporarily unavailable.</div></section>`;
    }
    const current = weather.current || {};
    const details = [];
    if (current.relative_humidity_2m !== undefined) details.push(`Humidity ${Math.round(Number(current.relative_humidity_2m))}%`);
    if (current.wind_speed_10m !== undefined) details.push(`Wind ${Math.round(Number(current.wind_speed_10m))} mph`);
    const days = (weather.days || []).map(day => {
      const date = localDate(day.date);
      const dow = date ? date.toLocaleDateString(undefined, {weekday:'short'}).toUpperCase() : '';
      const md = date ? date.toLocaleDateString(undefined, {month:'short', day:'numeric'}) : '';
      return `<div class="c17-forecast-day"><b>${esc(dow)}</b><small>${esc(md)}</small><span>${weatherIcon(day.code)}</span><strong>${Number.isFinite(Number(day.high)) ? Math.round(Number(day.high)) : '—'}°</strong><em>${Number.isFinite(Number(day.low)) ? Math.round(Number(day.low)) : '—'}°</em></div>`;
    }).join('');
    return `<section class="c17-weather"><div class="c17-weather-now"><div class="c17-weather-icon">${weatherIcon(current.weather_code)}</div><div><strong>${Number.isFinite(Number(current.temperature_2m)) ? Math.round(Number(current.temperature_2m)) : '—'}°F</strong><span>${esc(weatherLabel(current.weather_code))}</span><small>${esc(weather.location || 'C17 Cricket Academy')}${details.length ? ` · ${esc(details.join(' · '))}` : ''}</small></div></div><div class="c17-forecast">${days}</div></section>`;
  }

  async function enrollmentTrackerFromProcess2(data) {
    try {
      const rows = await requestJson('/api/cam/enrollments');
      const asOf = localDate(data.as_of) || new Date();
      const month = asOf.getMonth();
      const year = asOf.getFullYear();
      const current = (Array.isArray(rows) ? rows : []).filter(row => {
        const when = localDate(row.last_activity_at || row.sent_at || row.created_at);
        return when && when.getMonth() === month && when.getFullYear() === year;
      });
      const sentCount = (Array.isArray(rows) ? rows : []).filter(row => {
        const when = localDate(row.sent_at);
        return when && when.getMonth() === month && when.getFullYear() === year;
      }).length;
      data.registration_tracker = {
        links_sent_count: sentCount,
        tracker_count: current.length,
        rows: current.slice(0, 8).map(row => ({
          parent_name: [row.parent_first_name, row.parent_last_name].filter(Boolean).join(' ') || 'Parent / Guardian',
          sent_by: row.created_by_name || 'Academy Staff',
          sent_at: row.sent_at || null,
          activity_at: row.last_activity_at || row.sent_at || row.created_at || null,
          status: row.status || 'created',
          player_name: row.player_name || [row.player_first_name, row.player_last_name].filter(Boolean).join(' ') || 'Player',
          enrollment_id: row.id
        }))
      };
    } catch (error) {
      console.warn('Process 2 enrollment tracker unavailable; using dashboard fallback.', error);
    }
    return data;
  }

  function cardTitle(icon, title) {
    return `<div class="c17-card-title"><span class="c17-icon">${icon}</span><h2>${title}</h2></div>`;
  }

  function programCountsMarkup(data) {
    const counts = data.program_counts || {buckets:{}, total_players:0};
    const buckets = ['Beginners','U11','U13','U14','U15'];
    const cards = buckets.map((name, i) => `<div class="c17-program tone-${i+1}"><span>${esc(name)}</span><strong>${Number(counts.buckets?.[name] || 0)}</strong></div>`).join('');
    return `<article class="c17-card">${cardTitle('👥','Players in Programs')}<div class="c17-program-grid">${cards}<div class="c17-total"><span>Total Players</span><strong>${Number(counts.total_players || 0)}</strong><small>Active academy directory</small></div></div></article>`;
  }

  function assignmentMarkup(player) {
    if (player.batch_id) {
      const status = player.batch_status === 'waitlisted' ? 'Waitlisted' : 'Assigned';
      return `<span class="c17-assigned">${esc(status)} · ${esc(player.batch_name || 'Batch')}</span>`;
    }
    return `<button type="button" class="c17-primary c17-assign-batch" data-player-id="${Number(player.player_id)}">Assign Batch</button>`;
  }

  function newEnrollmentsMarkup(data) {
    const section = data.new_enrollments || {count:0, players:[]};
    const rows = (section.players || []).slice(0,5).map(player => `<tr data-player-id="${Number(player.player_id)}"><td><strong>${esc(player.player_name)}</strong><small>Enrollment complete</small></td><td>${esc(fmtDate(player.enrolled_date))}</td><td>${esc(player.parent_name || 'Parent / Guardian')}</td><td>${assignmentMarkup(player)}<div class="c17-batch-editor"></div></td></tr>`).join('');
    return `<article class="c17-card">${cardTitle('👤+',''+esc(data.month_label)+' - New Enrollment : '+Number(section.count || 0))}<div class="c17-table-wrap"><table><thead><tr><th>Player</th><th>Enrolled Date</th><th>Parent</th><th>Actions</th></tr></thead><tbody>${rows || '<tr><td colspan="4">No completed enrollments this month.</td></tr>'}</tbody></table></div></article>`;
  }

  function statusLabel(status) {
    const s = String(status || '').toLowerCase();
    if (s === 'completed') return 'Completed';
    if (['in_progress','documents_accepted','payment_method_added','opened'].includes(s)) return 'In Progress';
    if (s === 'sent') return 'Sent';
    if (s === 'created') return 'Created';
    if (s === 'approved') return 'Completed';
    return s.replace(/_/g,' ').replace(/\b\w/g, x => x.toUpperCase()) || 'Created';
  }

  function statusTone(status) {
    const label = statusLabel(status);
    if (label === 'Completed') return 'good';
    if (label === 'Sent') return 'blue';
    if (label === 'In Progress') return 'amber';
    return 'neutral';
  }

  function trackerMarkup(data) {
    const tracker = data.registration_tracker || {rows:[]};
    const rows = (tracker.rows || []).map(row => {
      const activity = row.activity_at || row.sent_at;
      const label = statusLabel(row.status);
      const action = label === 'Sent' ? 'Resend' : 'View';
      return `<tr><td>${esc(row.parent_name)}</td><td>${esc(row.sent_by)}</td><td><strong>${esc(activity ? new Date(activity).toLocaleString([], {month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'}) : 'Not sent')}</strong>${row.sent_at ? '<small>Enrollment link activity</small>' : '<small>Link not sent yet</small>'}</td><td><span class="c17-status ${statusTone(row.status)}">${esc(label)}</span></td><td>${esc(row.player_name)}</td><td><button type="button" class="c17-table-action" data-open-registration="1">${action}</button></td></tr>`;
    }).join('');
    return `<section class="c17-enrollment-grid"><article class="c17-card c17-links-card">${cardTitle('➤',esc(data.month_label)+' - Enrollment Links Sent : '+Number(tracker.links_sent_count || 0))}<div class="c17-links-number">${Number(tracker.links_sent_count || 0)}</div><p>Links sent this month</p></article><article class="c17-card c17-tracker-card">${cardTitle('✦','Enrollment Tracker : '+Number(tracker.tracker_count || 0))}<div class="c17-table-wrap"><table><thead><tr><th>Parent</th><th>Sent By</th><th>Sent / Activity</th><th>Status</th><th>Player</th><th>Actions</th></tr></thead><tbody>${rows || '<tr><td colspan="6">No enrollment-link activity this month.</td></tr>'}</tbody></table></div><button class="c17-link" data-open-registration="1">View all enrollment links →</button></article></section>`;
  }

  function sessionRows(rows = [], privateSession = false) {
    return rows.map(row => `<tr><td>${esc(privateSession ? (row.player_name || 'Player') : (row.batch_name || 'Group Session'))}</td><td>${esc(row.coach_name || 'Coach not assigned')}</td><td>${esc(row.location || 'Location not set')}</td><td>${esc(sessionTime(row.start_time, row.duration_minutes))}</td><td><button type="button" class="c17-table-action c17-take-attendance" data-session-id="${Number(row.id)}">Take Attendance</button></td></tr>`).join('');
  }

  function sessionsMarkup(data) {
    const sessions = data.sessions || {group:[], private:[], count:0};
    return `<article class="c17-card">${cardTitle('▣',esc(fmtDayDate(data.as_of))+' Sessions : '+Number(sessions.count || 0))}<div class="c17-session-grid"><section><h3>Group Sessions - ${sessions.group?.length || 0}</h3><div class="c17-table-wrap"><table><thead><tr><th>Batch</th><th>Coach</th><th>Venue</th><th>Time</th><th>Action</th></tr></thead><tbody>${sessionRows(sessions.group) || '<tr><td colspan="5">No group sessions scheduled today.</td></tr>'}</tbody></table></div></section><section><h3>1 on 1 Sessions - ${sessions.private?.length || 0}</h3><div class="c17-table-wrap"><table><thead><tr><th>Player</th><th>Coach</th><th>Venue</th><th>Time</th><th>Action</th></tr></thead><tbody>${sessionRows(sessions.private, true) || '<tr><td colspan="5">No 1 on 1 sessions scheduled today.</td></tr>'}</tbody></table></div></section></div></article>`;
  }

  function eventDateRange(start, end) {
    if (!start) return 'Date TBD';
    if (!end || end === start) return fmtDate(start, {weekday:'short'});
    return `${fmtDate(start, {weekday:'short'})} – ${fmtDate(end, {weekday:'short'})}`;
  }

  function eventRows(rows, type) {
    if (!rows?.length) return '<div class="c17-empty compact">No upcoming items.</div>';
    return rows.map(row => {
      if (type === 'match') return `<div class="c17-event-row"><span>🗓</span><div><strong>${esc(row.team_name || 'C17')} vs ${esc(row.opponent || 'Opponent')}</strong><small>${esc(fmtDate(row.match_date,{weekday:'short'}))} · ${esc(fmtTime(row.start_time))}</small><small>${esc(row.venue || 'Location TBD')}</small></div></div>`;
      if (type === 'program') return `<div class="c17-event-row"><span>▦</span><div><strong>${esc(row.name || 'Program')}</strong><small>${esc(eventDateRange(row.start_date,row.end_date))} · ${esc(fmtTime(row.start_time))}</small><small>${esc(row.location || 'Location TBD')}</small></div></div>`;
      return `<div class="c17-event-row"><span>🏆</span><div><strong>${esc(row.name || 'Tournament')}</strong><small>${esc(eventDateRange(row.start_date,row.end_date))} · All Day</small><small>${esc(row.location || 'Location TBD')}</small></div></div>`;
    }).join('');
  }

  function eventsMarkup(data) {
    const events = data.events || {};
    const col = (title, rows, type, tab) => `<section class="c17-event-col"><div class="c17-event-head"><h3>${esc(title)}</h3><button data-dashboard-tab="${esc(tab)}">View All →</button></div>${eventRows(rows,type)}</section>`;
    return `<article class="c17-card">${cardTitle('▣',esc(data.month_label)+' - Upcoming Events')}<div class="c17-events-grid">${col('Matches',events.matches,'match','teams')}${col('Camps / Programs',events.programs,'program','programs')}${col('Tournaments',events.tournaments,'tournament','tournaments')}</div></article>`;
  }

  function attendanceMarkup(data) {
    const attendance = data.attendance || {batches:[], total_scheduled:0};
    const rows = attendance.batches || [];
    const body = rows.map(row => `<tr><td><strong>${esc(row.batch)}</strong></td><td>${Number(row.scheduled || 0)}</td><td>${Number(row.present || 0)}</td><td>${Number(row.late || 0)}</td><td>${Number(row.absent || 0)}</td><td>${Number(row.not_recorded || 0)}</td><td><div class="c17-attendance-pct"><span>${Number(row.attendance_percent || 0).toFixed(1)}%</span><i><b style="width:${Math.max(0,Math.min(100,Number(row.attendance_percent||0)))}%"></b></i></div></td></tr>`).join('');
    const totals = rows.reduce((a,r) => {['scheduled','present','late','absent','not_recorded'].forEach(k => a[k]+=Number(r[k]||0)); return a;}, {scheduled:0,present:0,late:0,absent:0,not_recorded:0});
    const pct = totals.scheduled ? ((totals.present + totals.late) * 100 / totals.scheduled) : 0;
    const totalRow = rows.length ? `<tr class="c17-total-row"><td>Total</td><td>${totals.scheduled}</td><td>${totals.present}</td><td>${totals.late}</td><td>${totals.absent}</td><td>${totals.not_recorded}</td><td><strong>${pct.toFixed(1)}%</strong></td></tr>` : '';
    const title = attendance.date ? `${fmtDayDate(attendance.date)}${attendance.latest_time ? ` · ${fmtTime(attendance.latest_time)}` : ''} - Session Attendance : ${Number(attendance.total_scheduled || 0)}` : 'Session Attendance : 0';
    return `<article class="c17-card">${cardTitle('👥',esc(title))}<div class="c17-table-wrap"><table><thead><tr><th>Batch</th><th>Scheduled</th><th>Present</th><th>Late</th><th>Absent</th><th>Not Recorded</th><th>Attendance %</th></tr></thead><tbody>${body || '<tr><td colspan="7">No group-session attendance recorded yet.</td></tr>'}${totalRow}</tbody></table></div></article>`;
  }

  function moneyMetric(label, value, note, pending = false) {
    return `<div class="c17-money"><span>${esc(label)}</span><strong class="${pending?'pending':''}">${esc(money(value))}</strong><small>${esc(note)}</small></div>`;
  }

  function receiptsMarkup(data) {
    const r = data.receipts || {};
    return `<article class="c17-card">${cardTitle('＄',esc(data.month_label)+' - Academy Receipts')}<div class="c17-money-grid two">${moneyMetric('Group Session Fee Received',r.group_session_fee_received_cents,'Collected this month')}${moneyMetric('Group Session Fee Pending',r.group_session_fee_pending_cents,'Pending payments',true)}</div></article>`;
  }

  function paymentsMarkup(data) {
    const p = data.payments || {};
    return `<article class="c17-card">${cardTitle('▣',esc(data.month_label)+' - Academy Payments')}<div class="c17-money-grid three">${moneyMetric('Coach Salary Payments',p.coach_salary_payments_cents,'Paid this month')}${moneyMetric('Facility Payments',p.facility_payments_cents,'Paid this month')}${moneyMetric('Academy Expenses',p.academy_expenses_cents,'This month')}</div></article>`;
  }

  function dashboardMarkup(data, weather) {
    return `<div class="c17-dashboard"><section class="c17-hero"><div class="c17-welcome"><h1>Welcome, ${esc(data.user?.display_name || 'Admin')}</h1><p>C17 Academy Dashboard</p></div>${weatherMarkup(weather)}</section><section class="c17-two-col">${programCountsMarkup(data)}${newEnrollmentsMarkup(data)}</section>${trackerMarkup(data)}${sessionsMarkup(data)}${eventsMarkup(data)}${attendanceMarkup(data)}${receiptsMarkup(data)}${paymentsMarkup(data)}</div>`;
  }

  async function openBatchEditor(button) {
    const playerId = Number(button.dataset.playerId || 0);
    const row = button.closest('tr');
    const cell = button.closest('td');
    const player = lastData?.new_enrollments?.players?.find(item => Number(item.player_id) === playerId);
    if (!cell || !player) return;
    let editor = $('.c17-batch-editor', cell);
    if (!editor) { editor = document.createElement('div'); editor.className='c17-batch-editor'; cell.appendChild(editor); }
    editor.innerHTML = '<div class="c17-editor">Loading active batches…</div>';
    try {
      const batches = await requestJson('/api/cam/batches');
      const activeBatches = (Array.isArray(batches) ? batches : []).filter(batch => String(batch.status || '') === 'active');
      const options = activeBatches.map(batch => {
        const activeCount = Number(batch.active_player_count || 0), capacity = Number(batch.capacity || 0);
        const full = capacity > 0 && activeCount >= capacity;
        return `<option value="${Number(batch.id)}" ${full?'disabled':''}>${esc(batch.name || `Batch ${batch.id}`)}${capacity?` · ${activeCount}/${capacity}`:''}${full?' · Full':''}</option>`;
      }).join('');
      editor.innerHTML = `<form class="c17-editor"><label>Batch<select name="batch_id" required><option value="">Select batch</option>${options}</select></label><label>Start date<input type="date" name="joined_on" value="${esc(player.enrolled_date || lastData.as_of)}" required></label><div><button type="button" class="c17-secondary c17-cancel">Cancel</button><button type="submit" class="c17-primary">Confirm</button></div><small class="c17-editor-status"></small></form>`;
      $('.c17-cancel', editor).onclick = () => editor.remove();
      const form = $('form', editor);
      form.onsubmit = async event => {
        event.preventDefault();
        const fd = new FormData(form), batchId = Number(fd.get('batch_id') || 0), joinedOn = String(fd.get('joined_on') || '');
        if (!batchId) return;
        const status = $('.c17-editor-status', form); status.textContent='Assigning…';
        try {
          await requestJson(`/api/cam/batches/${batchId}/players`, {method:'POST', body:JSON.stringify({player_id:playerId,waitlist_if_full:false,joined_on:joinedOn})});
          notify(`${player.player_name} assigned to batch.`); await render(true);
        } catch (error) { status.textContent = error.message || 'Assignment failed.'; }
      };
    } catch (error) { editor.innerHTML = `<div class="c17-editor">${esc(error.message || 'Could not load batches.')}</div>`; }
  }

  function wire(root) {
    $$('.c17-assign-batch', root).forEach(button => button.onclick = () => openBatchEditor(button));
    $$('[data-open-registration]', root).forEach(button => button.onclick = () => { location.hash='cam?tab=registration'; });
    $$('[data-dashboard-tab]', root).forEach(button => button.onclick = () => go(button.dataset.dashboardTab));
    $$('.c17-take-attendance', root).forEach(button => button.onclick = () => { const sessionId = Number(button.dataset.sessionId || 0); if (sessionId) location.hash = `cam?tab=attendance&session_id=${encodeURIComponent(sessionId)}`; });
  }

  async function render(force = false) {
    if (!active() || rendering) return;
    const content = $('#camWorkspace .cam-content');
    if (!content) return;
    if (!force && content.dataset.dashboardV4 === '1' && $('.c17-dashboard', content)) return;
    rendering = true;
    document.body.classList.add('c17-dashboard-active');
    try {
      let data = await requestJson('/api/cam/dashboard/v3');
      data = await enrollmentTrackerFromProcess2(data);
      const weather = await loadWeather(data.academy || {});
      if (!active() || !content.isConnected) return;
      lastData = data;
      content.innerHTML = dashboardMarkup(data, weather);
      content.dataset.dashboardV4 = '1';
      wire(content);
    } catch (error) {
      content.innerHTML = `<div class="warning">Dashboard could not load: ${esc(error.message)}</div>`;
      content.dataset.dashboardV4 = '1';
    } finally { rendering = false; }
  }

  function apply() {
    scheduled = false;
    if (!active()) { document.body.classList.remove('c17-dashboard-active'); return; }
    document.body.classList.add('c17-dashboard-active');
    render(false);
  }

  function schedule() { if (scheduled) return; scheduled = true; requestAnimationFrame(apply); }
  window.addEventListener('hashchange', schedule);
  window.addEventListener('cam-payments-updated', () => render(true));
  window.addEventListener('cam-enrollment-completed', () => render(true));
  document.addEventListener('DOMContentLoaded', schedule);
  new MutationObserver(() => { if (active()) schedule(); }).observe(document.documentElement, {childList:true, subtree:true});
  schedule();
})();
