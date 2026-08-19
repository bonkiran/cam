(() => {
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  let scheduled=false;
  let weatherCache=null;
  let weatherCacheAt=0;
  let weatherPromise=null;

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    return {page:page||'dashboard',tab:new URLSearchParams(query).get('tab')||'overview'};
  }

  function dashboardActive(){
    const info=route();
    return info.page==='academy'&&info.tab==='overview';
  }

  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  function degree(value){
    if(value===null||value===undefined||value==='')return '—';
    const n=Number(value);
    return Number.isFinite(n)?`${Math.round(n)}°`:'—';
  }

  function number(value,digits=0){
    const n=Number(value);
    if(!Number.isFinite(n))return '—';
    return digits?n.toFixed(digits):String(Math.round(n));
  }

  function countryCode(value){
    const raw=String(value||'').trim();
    const aliases={
      'united states':'US','united states of america':'US','usa':'US','us':'US',
      'canada':'CA','ca':'CA','india':'IN','in':'IN',
      'united kingdom':'GB','uk':'GB','gb':'GB'
    };
    if(aliases[raw.toLowerCase()])return aliases[raw.toLowerCase()];
    return raw.length===2?raw.toUpperCase():'';
  }

  function uvDescription(value){
    const n=Number(value);
    if(!Number.isFinite(n))return null;
    if(n<=2)return 'Low';
    if(n<=5)return 'Moderate';
    if(n<=7)return 'High';
    if(n<=10)return 'Very High';
    return 'Extreme';
  }

  function weatherCodeLabel(value){
    const labels={
      0:'Clear sky',1:'Mainly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',48:'Rime fog',
      51:'Light drizzle',53:'Drizzle',55:'Heavy drizzle',61:'Light rain',63:'Rain',65:'Heavy rain',
      71:'Light snow',73:'Snow',75:'Heavy snow',80:'Rain showers',81:'Rain showers',82:'Heavy rain showers',
      95:'Thunderstorms',96:'Thunderstorms with hail',99:'Severe thunderstorms with hail'
    };
    const code=Number(value);
    return Number.isFinite(code)?(labels[code]||'Current conditions'):'Current conditions';
  }

  function heatIndexF(tempF,humidity){
    const t=Number(tempF),rh=Number(humidity);
    if(!Number.isFinite(t)||!Number.isFinite(rh))return null;
    if(t<80||rh<40)return Math.round(t*10)/10;
    let hi=-42.379+2.04901523*t+10.14333127*rh-0.22475541*t*rh-0.00683783*t*t-0.05481717*rh*rh+0.00122874*t*t*rh+0.00085282*t*rh*rh-0.00000199*t*t*rh*rh;
    if(rh<13&&t>=80&&t<=112){
      hi-=((13-rh)/4)*Math.sqrt(Math.max(0,(17-Math.abs(t-95))/17));
    }else if(rh>85&&t>=80&&t<=87){
      hi+=((rh-85)/10)*((87-t)/5);
    }
    return Math.round(hi*10)/10;
  }

  async function jsonFetch(url){
    const response=await fetch(url,{cache:'no-store'});
    let data=null;
    try{data=await response.json();}catch{}
    if(!response.ok)throw new Error(data?.reason||data?.detail||`Request failed (${response.status})`);
    return data||{};
  }

  async function academyProfile(){
    const data=await jsonFetch('/api/academy/profile');
    return data?.profile||null;
  }

  async function openMeteoLocation(profile){
    const city=String(profile?.city||'').trim();
    const state=String(profile?.state||'').trim();
    const postal=String(profile?.postal_code||'').trim();
    const code=countryCode(profile?.country);
    const terms=[];
    if(city&&state)terms.push(`${city}, ${state}`);
    if(city)terms.push(city);
    if(postal)terms.push(postal);

    for(const term of [...new Set(terms)]){
      const params=new URLSearchParams({name:term,count:'8',language:'en',format:'json'});
      if(code)params.set('countryCode',code);
      const data=await jsonFetch(`https://geocoding-api.open-meteo.com/v1/search?${params.toString()}`);
      const results=Array.isArray(data?.results)?data.results:[];
      if(!results.length)continue;
      if(city){
        const exact=results.find(item=>String(item?.name||'').trim().toLowerCase()===city.toLowerCase());
        if(exact)return exact;
      }
      if(postal){
        const byPostal=results.find(item=>Array.isArray(item?.postcodes)&&item.postcodes.map(String).includes(postal));
        if(byPostal)return byPostal;
      }
      return results[0];
    }
    return null;
  }

  async function loadOpenMeteoWeather(){
    const profile=await academyProfile();
    if(!profile||(!profile.city&&!profile.postal_code)){
      return {provider:'Open-Meteo',configured:true,status:'location_required',location:profile||{}};
    }

    const place=await openMeteoLocation(profile);
    if(!place||place.latitude===undefined||place.longitude===undefined){
      throw new Error('Open-Meteo could not resolve the academy location');
    }

    const params=new URLSearchParams({
      latitude:String(place.latitude),
      longitude:String(place.longitude),
      current:'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,uv_index,wind_speed_10m',
      temperature_unit:'fahrenheit',
      wind_speed_unit:'mph',
      timezone:'auto',
      forecast_days:'1'
    });
    const data=await jsonFetch(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);
    const current=data?.current||{};
    if(current.temperature_2m===undefined||current.temperature_2m===null){
      throw new Error('Open-Meteo did not return current temperature');
    }

    const humidity=current.relative_humidity_2m;
    const uv=current.uv_index;
    return {
      provider:'Open-Meteo',
      provider_mode:'browser_direct',
      configured:true,
      status:'ok',
      location:{
        city:profile.city||place.name,
        state:profile.state||place.admin1,
        postal_code:profile.postal_code||null,
        country:profile.country||place.country
      },
      temperature_f:current.temperature_2m,
      feels_like_f:current.apparent_temperature,
      heat_index_f:heatIndexF(current.temperature_2m,humidity),
      uv_index:uv,
      uv_description:uvDescription(uv),
      condition:weatherCodeLabel(current.weather_code),
      humidity,
      wind_mph:current.wind_speed_10m,
      observed_at:current.time
    };
  }

  async function currentWeather(){
    const now=Date.now();
    const cacheMs=weatherCache?.status==='ok'?10*60*1000:60*1000;
    if(weatherCache&&now-weatherCacheAt<cacheMs)return weatherCache;
    if(weatherPromise)return weatherPromise;
    weatherPromise=loadOpenMeteoWeather()
      .then(data=>{
        weatherCache=data||{configured:true,status:'unavailable'};
        weatherCacheAt=Date.now();
        return weatherCache;
      })
      .catch(error=>{
        console.warn('Direct Open-Meteo weather request failed:',error);
        weatherCache={provider:'Open-Meteo',provider_mode:'browser_direct',configured:true,status:'unavailable'};
        weatherCacheAt=Date.now();
        return weatherCache;
      })
      .finally(()=>{weatherPromise=null;});
    return weatherPromise;
  }

  function weatherMarkup(data){
    const status=data?.status||'unavailable';
    if(status==='ok'){
      const location=[data.location?.city,data.location?.state].filter(Boolean).join(', ');
      const details=[];
      if(data.humidity!==null&&data.humidity!==undefined)details.push(`Humidity ${number(data.humidity)}%`);
      if(data.wind_mph!==null&&data.wind_mph!==undefined)details.push(`Wind ${number(data.wind_mph)} mph`);
      const provider=data.provider_mode==='browser_direct'?'Open-Meteo live':data.provider||'Live weather';
      return `<div class="cam-weather-primary"><span>Weather${location?` · ${esc(location)}`:''}</span><strong>${esc(degree(data.temperature_f))}</strong><small>${esc(data.condition||'Current conditions')}${details.length?` · ${esc(details.join(' · '))}`:''}</small><em>${esc(provider)}</em></div>
        <div class="cam-weather-measure"><span>Feels Like</span><strong>${esc(degree(data.feels_like_f))}</strong><small>Current comfort</small></div>
        <div class="cam-weather-measure"><span>Heat Index</span><strong>${esc(degree(data.heat_index_f))}</strong><small>${data.humidity!==null&&data.humidity!==undefined?`${esc(number(data.humidity))}% humidity`:'Current'}</small></div>
        <div class="cam-weather-measure cam-weather-uv"><span>UV Index</span><strong>${data.uv_index!==null&&data.uv_index!==undefined?esc(number(data.uv_index,1)):'—'}</strong><small>${esc(data.uv_description||'Rating unavailable')}</small></div>`;
    }
    let title='Weather temporarily unavailable',note='Live weather will retry automatically.';
    if(status==='location_required'){title='Academy location needed';note='Add the academy city or ZIP in Academy Profile.';}
    return `<div class="cam-weather-primary cam-weather-muted"><span>Weather</span><strong>${esc(title)}</strong><small>${esc(note)}</small></div>
      <div class="cam-weather-measure cam-weather-muted"><span>Feels Like</span><strong>—</strong><small>Pending</small></div>
      <div class="cam-weather-measure cam-weather-muted"><span>Heat Index</span><strong>—</strong><small>Pending</small></div>
      <div class="cam-weather-measure cam-weather-muted"><span>UV Index</span><strong>—</strong><small>Pending</small></div>`;
  }

  async function ensureWeather(){
    if(!dashboardActive())return;
    const hero=$('#academyWorkspace .academy-dashboard-welcome');
    if(!hero)return;
    const actions=$('.academy-hero-actions',hero);
    if(!actions)return;
    let card=$('.cam-dashboard-current-weather',hero);
    if(!card){
      card=document.createElement('section');
      card.className='cam-dashboard-current-weather';
      card.setAttribute('aria-label','Current academy weather');
      card.innerHTML='<div class="cam-weather-primary cam-weather-muted"><span>Weather</span><strong>Loading…</strong><small>Current academy conditions</small></div><div class="cam-weather-measure cam-weather-muted"><span>Feels Like</span><strong>—</strong><small>Loading</small></div><div class="cam-weather-measure cam-weather-muted"><span>Heat Index</span><strong>—</strong><small>Loading</small></div><div class="cam-weather-measure cam-weather-muted"><span>UV Index</span><strong>—</strong><small>Loading</small></div>';
      actions.before(card);
    }
    if(card.dataset.weatherLoaded==='1')return;
    card.dataset.weatherLoaded='loading';
    const data=await currentWeather();
    if(!card.isConnected||!dashboardActive())return;
    card.innerHTML=weatherMarkup(data);
    card.dataset.weatherLoaded='1';
  }

  function exactElement(root,text){
    return $$('h1,h2,h3,h4,strong,b,span,div',root).find(node=>node.children.length===0&&(node.textContent||'').trim()===text)||null;
  }

  function monthName(){
    return new Intl.DateTimeFormat('en-US',{month:'long'}).format(new Date());
  }

  function polishDashboardLabels(){
    if(!dashboardActive())return;
    const content=$('#academyWorkspace .academy-content');
    if(!content)return;

    const batches=exactElement(content,'Batch Breakdown');
    if(batches)batches.textContent='Batches';

    const registrations=exactElement(content,'New Player Registrations');
    if(registrations){
      const panel=registrations.closest('article,.panel,section')||registrations.parentElement;
      const count=panel?$$('strong,b,span,div',panel).find(node=>{
        if(node===registrations||node.children.length)return false;
        const text=(node.textContent||'').trim();
        return /^\d+$/.test(text)&&Number(text)>=0;
      }):null;
      if(count){
        registrations.textContent=`New Player Registrations: ${count.textContent.trim()}`;
        count.classList.add('cam-registration-count-hidden');
      }
    }

    const outgoings=exactElement(content,'Current Month Academy Outgoings');
    if(outgoings)outgoings.textContent=`Academy Payments in ${monthName()}`;

    $$('button',content).forEach(button=>{
      const text=(button.textContent||'').trim();
      if(text==='Fees & Payments')button.textContent='Finance';
      if(text==='Teams & Matches')button.textContent='Matches';
      if(text==='Sessions')button.textContent='Programs & Sessions';
    });
  }

  function apply(){
    scheduled=false;
    if(!dashboardActive())return;
    polishDashboardLabels();
    ensureWeather();
  }

  function schedule(){
    if(scheduled)return;
    scheduled=true;
    requestAnimationFrame(apply);
  }

  window.addEventListener('hashchange',schedule);
  document.addEventListener('DOMContentLoaded',schedule);
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
  schedule();
})();
