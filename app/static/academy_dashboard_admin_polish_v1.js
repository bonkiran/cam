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
    return digits? n.toFixed(digits) : String(Math.round(n));
  }

  async function currentWeather(){
    const now=Date.now();
    if(weatherCache&&now-weatherCacheAt<10*60*1000)return weatherCache;
    if(weatherPromise)return weatherPromise;
    weatherPromise=fetch('/api/academy/weather/current',{cache:'no-store'})
      .then(async response=>{
        let data=null;try{data=await response.json();}catch{}
        if(!response.ok)throw new Error(data?.detail||`Weather request failed (${response.status})`);
        weatherCache=data||{};weatherCacheAt=Date.now();return weatherCache;
      })
      .catch(()=>({configured:true,status:'unavailable'}))
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
      const provider=data.provider_mode==='no_key_fallback'?'Live pilot feed':data.provider||'Live weather';
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
