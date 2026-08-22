(() => {
  let contextPromise = null;
  let weatherCache = null;
  let weatherCacheAt = 0;

  function esc(value = '') {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  async function requestJson(url) {
    const response = await fetch(url, {cache:'no-store'});
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    return data;
  }

  function localDate(value) {
    if (!value) return null;
    const raw = String(value);
    const date = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? new Date(`${raw}T12:00:00`) : new Date(raw);
    return Number.isNaN(date.getTime()) ? null : date;
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

  async function camContext() {
    if (!contextPromise) contextPromise = requestJson('/api/cam/dashboard/v3');
    return contextPromise;
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
      console.warn('C17 page weather unavailable:', error);
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

  async function hero({title='Enrollment', subtitle='C17 Academy Enrollment'} = {}) {
    let context = {};
    try { context = await camContext(); } catch (error) { console.warn('C17 page context unavailable:', error); }
    const weather = await loadWeather(context?.academy || {});
    return `<section class="c17-hero c17-page-hero"><div class="c17-welcome"><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div>${weatherMarkup(weather)}</section>`;
  }

  window.C17AcademyHeader = {hero};
})();