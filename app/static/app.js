const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const state = { dashboard:null, videos:[], players:[], currentVideo:null, frames:[], events:[] };
const navItems = [
  ['dashboard','⌂','Dashboard'],['upload','⇧','Upload Video'],['analyses','▣','My Analyses'],
  ['players','♙','Players'],['comparisons','⇄','Comparisons'],['shot-library','◫','Shot Library'],
  ['reports','▤','Reports'],['insights','⌁','Insights'],['sessions','▦','Sessions'],
  ['settings','⚙','Settings'],['integrations','✚','Integrations'],['help','?','Help & Support']
];

function shell(content, active='dashboard'){
  return `<div class="app">
    <aside class="sidebar" id="sidebar"><div><div class="brand"><div class="mark">🏏</div><div>CRICK<span>ANALYSIS</span></div></div>
      <nav class="nav">${navItems.map(([id,icon,label])=>`<button data-route="${id}" class="${active===id?'active':''}"><i>${icon}</i><b>${label}</b></button>`).join('')}</nav></div>
      <div class="profile"><div class="avatar">GK</div><div><strong>Gayatri Kalina</strong><small>CrickAnalysis MVP</small></div></div>
    </aside>
    <main class="main"><header class="topbar"><button class="mobile-menu" id="mobileMenu">☰</button>
      <div class="search"><span>⌕</span><input id="globalSearch" placeholder="Search analyses, players..." /></div>
      <button class="top-chip">CrickAnalysis⌄</button></header>${content}</main>
  </div>`;
}

async function api(url, options={}){
  const res = await fetch(url, options);
  if(!res.ok){let msg=`Request failed (${res.status})`;try{const data=await res.json();msg=data.detail||msg}catch{}throw new Error(msg)}
  if(res.status===204) return null;
  return res.json();
}
function toast(msg){const el=$('#toast');el.textContent=msg;el.classList.add('show');clearTimeout(window.__toast);window.__toast=setTimeout(()=>el.classList.remove('show'),2600)}
function fmtTime(s=0){s=Number(s)||0;const m=Math.floor(s/60);const sec=(s%60).toFixed(2).padStart(5,'0');return `${m}:${sec}`}
function fileSize(bytes=0){if(bytes<1024*1024)return `${(bytes/1024).toFixed(1)} KB`;return `${(bytes/1024/1024).toFixed(1)} MB`}
function thumbStyle(v){return v.thumbnail_path?`style="background-image:url('${v.thumbnail_path}')"`:''}
function statusPill(v){return `<span class="pill ${v.status}">${v.status}</span>`}
function route(){const raw=location.hash.replace(/^#/,'')||'dashboard';const [page,query='']=raw.split('?');return {page,params:new URLSearchParams(query)}}
function navigate(target){location.hash=target}

function wireShell(active){
  $$('.nav button').forEach(b=>b.onclick=()=>navigate(b.dataset.route));
  $('#mobileMenu').onclick=()=>$('#sidebar').classList.toggle('open');
  const search=$('#globalSearch'); if(search) search.oninput=()=>{const q=search.value.toLowerCase();$$('[data-search]').forEach(el=>el.classList.toggle('hidden',!el.dataset.search.toLowerCase().includes(q)))};
}

async function loadDashboard(){state.dashboard=await api('/api/dashboard');}
async function loadVideos(){state.videos=await api('/api/videos');}
async function loadPlayers(){state.players=await api('/api/players');}

function pageHead(title,subtitle,action=''){
  return `<section class="page-head"><div><h1>${title}</h1><p>${subtitle}</p></div>${action}</section>`;
}

async function renderDashboard(){
  await loadDashboard(); const d=state.dashboard;
  const content=`${pageHead('Dashboard','Real uploaded-video analysis status and cricket events.',`<button class="primary" id="uploadNow">＋ Upload New Video</button>`)}
  <section class="stats">
    <div class="stat"><div class="stat-icon purple">▣</div><div><strong>${d.video_count}</strong><span>Videos</span><small>${d.completed_count} analyzed</small></div></div>
    <div class="stat"><div class="stat-icon blue">♙</div><div><strong>${d.player_count}</strong><span>Players</span><small>Persistent profiles</small></div></div>
    <div class="stat"><div class="stat-icon green">↗</div><div><strong>${d.boundaries}</strong><span>Tagged Boundaries</span><small>Fours + sixes</small></div></div>
    <div class="stat"><div class="stat-icon amber">★</div><div><strong>${d.sixes}</strong><span>Tagged Sixes</span><small>Evidence-ready events</small></div></div>
  </section>
  <section class="grid"><div class="column">
    <article class="panel"><div class="panel-head"><div><h2>What the MVP analyzes now</h2><p>Every value below comes from the uploaded video or a user tag.</p></div></div>
      <div class="metric-grid"><div class="metric"><span>Video metadata</span><strong>Real FPS</strong></div><div class="metric"><span>Computer vision</span><strong>Motion timeline</strong></div><div class="metric"><span>Evidence</span><strong>Key frames</strong></div><div class="metric"><span>Manual truth labels</span><strong>4 / 6 / events</strong></div></div>
      <p class="note">Motion peaks are candidate moments only. They are not presented as automatically recognized cricket shots. That classifier is the next model slice.</p>
    </article>
    <article class="panel"><div class="panel-head"><div><h2>Core build sequence</h2><p>Moving from evidence capture to cricket-specific intelligence.</p></div></div>
      <div class="metric-grid"><div class="metric"><span>Phase 1</span><strong>Upload + frames ✓</strong></div><div class="metric"><span>Phase 2</span><strong>Delivery detection</strong></div><div class="metric"><span>Phase 3</span><strong>4 / 6 AI</strong></div><div class="metric"><span>Phase 4</span><strong>Pose + bat/ball</strong></div></div>
    </article>
  </div><div class="column"><article class="panel recent"><div class="panel-head"><h2>Recent Analyses</h2><button class="link" id="viewAll">View all</button></div>${recentRows(d.recent)}</article></div></section>`;
  $('#app').innerHTML=shell(content,'dashboard'); wireShell('dashboard');
  $('#uploadNow').onclick=()=>navigate('upload'); $('#viewAll').onclick=()=>navigate('analyses'); wireVideoRows();
}

function recentRows(videos){
  if(!videos.length)return `<div class="empty"><strong>No videos yet</strong>Upload a cricket video to start the real analysis pipeline.</div>`;
  return videos.map(v=>`<div class="video-row" data-search="${(v.original_name+' '+(v.player_name||'')).toLowerCase()}"><div class="thumb" ${thumbStyle(v)}></div><div class="video-copy"><h3>${v.original_name}</h3><p>${v.player_name||'Unknown Player'} · ${v.duration?fmtTime(v.duration):'processing'}</p>${statusPill(v)}</div><button class="link open-video" data-id="${v.id}">Open →</button></div>`).join('');
}
function wireVideoRows(){ $$('.open-video').forEach(b=>b.onclick=()=>navigate(`analysis?id=${b.dataset.id}`)); }

function renderUpload(){
  const content=`${pageHead('Upload Video','Upload real cricket footage. The backend stores it, reads metadata and generates evidence frames.')}
  <article class="panel upload-card"><div class="warning"><b>Phase-1 truthfulness rule:</b> motion peaks are candidates, not automatically recognized shots. We will add the cricket classifier as a separate validated model.</div><br/>
    <form id="uploadForm"><div class="field"><label>Player name</label><input name="player_name" value="Vaibhav Suryavanshi" required maxlength="100" /></div>
      <label class="dropzone"><strong>Select cricket video</strong><p class="note">MP4, MOV, M4V, AVI, WebM or MKV · local MVP limit 2 GB</p><input id="videoFile" name="file" type="file" accept="video/*" required /></label>
      <div class="progress hidden" id="progress"><div></div></div><p class="note" id="uploadStatus"></p><br/><button class="primary" type="submit">Upload & Analyze</button></form>
  </article>`;
  $('#app').innerHTML=shell(content,'upload');wireShell('upload');
  $('#uploadForm').onsubmit=uploadVideo;
}

function uploadVideo(e){
  e.preventDefault(); const form=e.currentTarget; const fd=new FormData(form); const file=$('#videoFile').files[0]; if(!file)return;
  const progress=$('#progress'), bar=$('#progress div'), status=$('#uploadStatus');progress.classList.remove('hidden');status.textContent=`Uploading ${file.name} (${fileSize(file.size)})…`;
  const xhr=new XMLHttpRequest(); xhr.open('POST','/api/videos');
  xhr.upload.onprogress=ev=>{if(ev.lengthComputable)bar.style.width=`${Math.round(ev.loaded/ev.total*100)}%`};
  xhr.onerror=()=>toast('Upload failed.');
  xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300){const v=JSON.parse(xhr.responseText);bar.style.width='100%';status.textContent='Upload complete. Analysis started…';toast('Video uploaded. Processing frames now.');setTimeout(()=>navigate(`analysis?id=${v.id}`),500)}else{try{toast(JSON.parse(xhr.responseText).detail)}catch{toast('Upload failed')}}};
  xhr.send(fd);
}

async function renderAnalyses(){
  await loadVideos(); const content=`${pageHead('My Analyses','All uploaded cricket videos and their real processing status.',`<button class="primary" id="newUpload">＋ Upload Video</button>`)}<article class="panel recent">${recentRows(state.videos)}</article>`;
  $('#app').innerHTML=shell(content,'analyses');wireShell('analyses');wireVideoRows();$('#newUpload').onclick=()=>navigate('upload');
}

async function renderPlayers(){
  await loadPlayers();const cards=state.players.length?state.players.map(p=>`<article class="player-card" data-search="${p.name.toLowerCase()}"><h3>${p.name}</h3><p>${p.video_count} video(s) · ${p.completed_analyses||0} completed analysis(es)</p></article>`).join(''):`<div class="empty"><strong>No players yet</strong>Players are created automatically when you upload their first video.</div>`;
  $('#app').innerHTML=shell(`${pageHead('Players','Player profiles are persisted from real uploads.')}<section class="players-grid">${cards}</section>`,'players');wireShell('players');
}

async function renderAnalysis(id){
  const [video,frames,events]=await Promise.all([api(`/api/videos/${id}`),api(`/api/videos/${id}/frames`),api(`/api/videos/${id}/events`)]);state.currentVideo=video;state.frames=frames;state.events=events;
  const action=`<button class="secondary" id="reanalyse">Re-analyze</button>`;
  const body=video.status==='complete'?analysisWorkspace(video,frames,events):processingView(video);
  $('#app').innerHTML=shell(`${pageHead(video.original_name,`${video.player_name||'Unknown Player'} · ${statusPill(video)}`,action)}${body}`,'analyses');wireShell('analyses');
  $('#reanalyse').onclick=async()=>{await api(`/api/videos/${id}/reanalyze`,{method:'POST'});toast('Re-analysis started.');setTimeout(()=>renderAnalysis(id),700)};
  if(video.status==='complete')wireAnalysis(id); else if(video.status==='processing'||video.status==='uploaded')setTimeout(()=>renderAnalysis(id),1500);
}

function processingView(v){return `<article class="panel"><div class="empty"><span class="spinner"></span><strong>${v.status==='failed'?'Analysis failed':'Analyzing video…'}</strong>${v.status==='failed'?`<p>${v.error||'Unknown error'}</p>`:`<p>Reading FPS, duration, resolution, motion timeline and evidence frames.</p>`}</div></article>`}

function analysisWorkspace(v,frames,events){
  return `<section class="analysis-layout"><div class="column"><article class="panel"><div class="video-stage"><video id="player" controls preload="metadata" src="${v.video_url}"></video><div class="transport"><button data-step="-10">−10f</button><button data-step="-1">−1 frame</button><button data-step="1">+1 frame</button><button data-step="10">+10f</button><button id="evidence">Extract evidence sequence</button><span class="time" id="timeReadout">0:00.00 / ${fmtTime(v.duration)}</span></div></div></article>
    <article class="panel"><div class="panel-head"><div><h2>Video Metadata</h2><p>Read directly from the source file.</p></div></div><div class="metric-grid"><div class="metric"><span>FPS</span><strong>${Number(v.fps).toFixed(3)}</strong></div><div class="metric"><span>Duration</span><strong>${fmtTime(v.duration)}</strong></div><div class="metric"><span>Resolution</span><strong>${v.width}×${v.height}</strong></div><div class="metric"><span>Frames</span><strong>${v.frame_count.toLocaleString()}</strong></div></div></article>
    <article class="panel"><div class="panel-head"><div><h2>Motion Timeline</h2><p>Computer-vision frame difference; useful for locating candidate action moments.</p></div><span class="candidate-label">Not yet a cricket-shot classifier</span></div><div class="motion-chart"><canvas id="motionCanvas"></canvas></div></article>
    <article class="panel"><div class="panel-head"><div><h2>Generated Frames</h2><p>Gold border = motion-peak candidate. Click a frame to seek the video.</p></div><label class="note"><input type="checkbox" id="candidateOnly"> candidates only</label></div><div class="frame-strip" id="frameStrip">${frameCards(frames)}</div></article>
    <article class="panel"><div class="panel-head"><div><h2>Evidence Sequence</h2><p>Exact frames extracted around the current video position.</p></div></div><div id="sequence" class="sequence"><div class="empty" style="grid-column:1/-1"><strong>No sequence yet</strong>Seek to a shot/contact moment and choose “Extract evidence sequence”.</div></div></article>
    </div><div class="column"><article class="panel"><div class="panel-head"><div><h2>Tag Cricket Event</h2><p>These labels create ground truth for later AI training/validation.</p></div></div><div class="tag-grid">${['four','six','dot','single','two','three','wicket','other'].map(t=>`<button class="${t}" data-event="${t}">${labelEvent(t)}</button>`).join('')}</div><div class="field" style="margin-top:12px"><label>Optional note</label><textarea id="eventNote" rows="3" placeholder="e.g. pull over mid-wicket; front leg opens early"></textarea></div></article>
    <article class="panel"><div class="panel-head"><h2>Tagged Events</h2><span>${events.length}</span></div><div class="events" id="eventsList">${eventRows(events)}</div></article></div></section>`;
}
function frameCards(frames){if(!frames.length)return `<div class="empty">No generated frames.</div>`;return frames.map(f=>`<button class="frame-card ${f.is_candidate?'candidate':''}" data-time="${f.timestamp}" data-candidate="${f.is_candidate}"><img src="${f.image_path}" loading="lazy"><span>${fmtTime(f.timestamp)} ${f.is_candidate?'<b>candidate</b>':''}</span></button>`).join('')}
function eventRows(events){if(!events.length)return `<div class="empty"><strong>No events tagged</strong>Use the buttons above at the exact video timestamp.</div>`;return events.map(e=>`<div class="event"><span class="event-type ${e.event_type}">${labelEvent(e.event_type)}</span><div class="event-copy"><strong>${fmtTime(e.timestamp)}</strong><small>${e.notes||e.label||'No note'}</small></div><button class="danger delete-event" data-id="${e.id}">×</button></div>`).join('')}
function labelEvent(t){return ({four:'FOUR',six:'SIX',dot:'DOT',single:'1 RUN',two:'2 RUNS',three:'3 RUNS',wicket:'WICKET',other:'OTHER'})[t]||t.toUpperCase()}

function wireAnalysis(id){
  const v=state.currentVideo, player=$('#player');
  player.ontimeupdate=()=>{$('#timeReadout').textContent=`${fmtTime(player.currentTime)} / ${fmtTime(v.duration)}`};
  $$('[data-step]').forEach(b=>b.onclick=()=>{const frames=Number(b.dataset.step);player.currentTime=Math.max(0,Math.min(v.duration,player.currentTime+frames/v.fps));player.pause()});
  $$('.frame-card').forEach(b=>b.onclick=()=>{player.currentTime=Number(b.dataset.time);player.pause();window.scrollTo({top:0,behavior:'smooth'})});
  $('#candidateOnly').onchange=e=>{$$('.frame-card').forEach(c=>c.classList.toggle('hidden',e.target.checked&&c.dataset.candidate!=='1'))};
  $$('[data-event]').forEach(b=>b.onclick=async()=>{const payload={timestamp:player.currentTime,event_type:b.dataset.event,notes:$('#eventNote').value.trim()||null};await api(`/api/videos/${id}/events`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});toast(`${labelEvent(b.dataset.event)} tagged at ${fmtTime(player.currentTime)}`);const events=await api(`/api/videos/${id}/events`);state.events=events;$('#eventsList').innerHTML=eventRows(events);wireDeleteEvents(id)});
  $('#evidence').onclick=async()=>{const btn=$('#evidence');btn.disabled=true;btn.textContent='Extracting…';try{const res=await api(`/api/videos/${id}/extract-sequence`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({center_timestamp:player.currentTime})});$('#sequence').innerHTML=res.frames.map(f=>`<figure><img src="${f.image_url}"><figcaption>${f.offset>=0?'+':''}${f.offset.toFixed(2)}s · frame ${f.frame_number}</figcaption></figure>`).join('');toast('Evidence sequence extracted from the source video.')}finally{btn.disabled=false;btn.textContent='Extract evidence sequence'}};
  wireDeleteEvents(id);drawMotion(v.motion||[]);
}
function wireDeleteEvents(videoId){$$('.delete-event').forEach(b=>b.onclick=async()=>{await api(`/api/events/${b.dataset.id}`,{method:'DELETE'});const events=await api(`/api/videos/${videoId}/events`);state.events=events;$('#eventsList').innerHTML=eventRows(events);wireDeleteEvents(videoId);toast('Event deleted.')})}
function drawMotion(samples){const canvas=$('#motionCanvas');if(!canvas)return;const rect=canvas.getBoundingClientRect();const dpr=devicePixelRatio||1;canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);ctx.strokeStyle='#edf0f5';for(let i=1;i<5;i++){const y=i*h/5;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke()}if(samples.length<2)return;const max=Math.max(...samples.map(s=>s.score),1);const maxT=Math.max(...samples.map(s=>s.t),1);ctx.beginPath();samples.forEach((s,i)=>{const x=s.t/maxT*w,y=h-(s.score/max)*(h-10)-5;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.strokeStyle='#6655f7';ctx.lineWidth=2;ctx.stroke()}

function renderPlaceholder(page){const label=navItems.find(x=>x[0]===page)?.[2]||'Page';const content=`${pageHead(label,'This module is part of the real application shell and will be implemented after the core video-analysis workflow.')}<article class="panel"><div class="empty"><strong>${label}</strong>Not implemented yet. Core engineering is currently focused on Upload → Frames → Events → Cricket AI.</div></article>`;$('#app').innerHTML=shell(content,page);wireShell(page)}

async function router(){try{const {page,params}=route();if(page==='dashboard')return renderDashboard();if(page==='upload')return renderUpload();if(page==='analyses')return renderAnalyses();if(page==='players')return renderPlayers();if(page==='analysis'){const id=params.get('id');if(!id)return navigate('analyses');return renderAnalysis(id)}return renderPlaceholder(page)}catch(err){console.error(err);$('#app').innerHTML=shell(`<article class="panel"><div class="empty"><strong>Something went wrong</strong>${err.message}</div></article>`,'dashboard');wireShell('dashboard');toast(err.message)}}
window.addEventListener('hashchange',router);window.addEventListener('resize',()=>{if($('#motionCanvas')&&state.currentVideo)drawMotion(state.currentVideo.motion||[])});router();
