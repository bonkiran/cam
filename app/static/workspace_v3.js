(() => {
  const REFERENCES = [
    {name:'CricVision', url:'https://cricvision.ai/', desc:'Cricket-focused AI video coaching and automated session analysis.', tags:['Cricket AI','Video']},
    {name:'CrickCoach AI', url:'https://www.crickcoachai.com/', desc:'AI-powered cricket technique and biomechanics feedback.', tags:['Cricket AI','Biomechanics']},
    {name:'PoseForge', url:'https://github.com/DataVisards/PoseForge', desc:'Open-source editable 3D pose analytics research for sports coaching.', tags:['Open Source','3D Pose']},
    {name:'Fulltrack AI', url:'https://www.fulltrack.ai/', desc:'Cricket ball tracking, auto-clipping, speed, swing and pitch maps.', tags:['Cricket','Ball Tracking']},
    {name:'StanceBeam', url:'https://www.stancebeam.com/', desc:'Cricket bat sensor and batting-performance analytics.', tags:['Cricket','Sensor']},
    {name:'Crickzy AI Coach', url:'https://www.crickzy.com/', desc:'AI cricket coaching and video-analysis service.', tags:['Cricket AI','Coaching']},
    {name:'Onform', url:'https://onform.com/', desc:'Mobile sports video analysis, slow motion, annotation and sharing.', tags:['Video','Coaching']},
    {name:'Dartfish', url:'https://www.dartfish.com/', desc:'Established sports video analysis and performance-review platform.', tags:['Video','Performance']},
    {name:'Kinovea', url:'https://www.kinovea.org/', desc:'Free open-source sports video annotation, tracking and measurement.', tags:['Open Source','Video']},
    {name:'Hudl Sportscode', url:'https://www.hudl.com/products/hudlsportscode', desc:'Professional customizable performance-analysis workflows.', tags:['Pro Analysis','Video']},
    {name:'Nacsport', url:'https://www.nacsport.com/', desc:'Sports video coding, tagging, presentations and analysis workflows.', tags:['Video','Team Analysis']},
    {name:'LongoMatch', url:'https://longomatch.com/en/', desc:'Video analysis and event tagging for coaches, analysts and players.', tags:['Video','Tagging']},
    {name:'Sportsbox 3D Golf', url:'https://sportsbox.ai/', desc:'Single-video markerless 3D movement analysis reference from golf.', tags:['3D Motion','Reference']},
    {name:'b4-app', url:'https://www.b4-app.com/', desc:'Baseball batting lab with swing, timing and contact analytics.', tags:['Batting','Reference']},
    {name:'Skillest', url:'https://skillest.com/', desc:'Remote sports coaching platform with video feedback and messaging.', tags:['Coaching','Video']},
    {name:'VisualEyes', url:'https://www.visualeyesapp.com/', desc:'Frame-by-frame coaching video, comparison and annotation tools.', tags:['Video','Coaching']},
  ];

  const chatHistory = [
    {role:'assistant', text:'Ask me about cricket or how to use CrickAnalysis. I also know which page, player/video and timestamp you are currently reviewing.'}
  ];
  let config = null;
  let uploadObjectUrl = null;
  let enhanceTimer = null;

  const qs = (s, root=document) => root.querySelector(s);
  const qsa = (s, root=document) => [...root.querySelectorAll(s)];
  const currentPage = () => (location.hash.replace(/^#/, '').split('?')[0] || 'dashboard');

  async function loadConfig(){
    if(config) return config;
    try{
      const res = await fetch('/api/config', {cache:'no-store'});
      if(res.ok) config = await res.json();
    }catch(_){ }
    return config || {};
  }

  function getContext(){
    const context = {page:currentPage(), route:location.hash || '#dashboard'};
    try{
      if(currentPage()==='analysis' && typeof state !== 'undefined' && state.currentVideo){
        const v = state.currentVideo;
        context.video = {id:v.id, name:v.original_name, player:v.player_name, mode:v.analysis_mode, status:v.status, fps:v.fps, duration:v.duration};
      }
    }catch(_){ }
    const video = qs('#player');
    if(video) context.current_timestamp = Number(video.currentTime || 0).toFixed(3);
    return context;
  }

  function contextLabel(){
    const ctx = getContext();
    if(ctx.video) return `${ctx.video.player || 'Player'} · ${ctx.video.name} · ${Number(ctx.current_timestamp || 0).toFixed(2)}s`;
    const labels = {dashboard:'Dashboard',upload:'Upload Video',analyses:'My Analyses',players:'Players',integrations:'Integrations'};
    return labels[ctx.page] || ctx.page.replace(/-/g,' ');
  }

  function renderChat(){
    const box = qs('#aiMessages'); if(!box) return;
    box.innerHTML='';
    chatHistory.forEach(msg=>{
      const el=document.createElement('div'); el.className=`ai-message ${msg.role}`; el.textContent=msg.text;
      if(msg.meta){const meta=document.createElement('span');meta.className='ai-meta';meta.textContent=msg.meta;el.appendChild(meta)}
      box.appendChild(el);
    });
    box.scrollTop=box.scrollHeight;
  }

  async function sendAiMessage(text){
    const clean=(text||'').trim(); if(!clean) return;
    chatHistory.push({role:'user',text:clean}); renderChat();
    const form=qs('#aiForm'), textarea=qs('#aiInput'), send=qs('#aiSend');
    if(textarea) textarea.value=''; if(send) send.disabled=true;
    chatHistory.push({role:'assistant',text:'Thinking…',meta:'', loading:true}); renderChat();
    const loadingIndex=chatHistory.length-1;
    try{
      const res=await fetch('/api/assistant',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:clean,context:getContext()})});
      let body={}; try{body=await res.json()}catch(_){ }
      if(!res.ok) throw new Error(body.detail || `Assistant request failed (${res.status})`);
      chatHistory[loadingIndex]={role:'assistant',text:body.answer,meta:body.mode==='ai'?'Crick AI · live cricket knowledge':'CrickAnalysis help'};
    }catch(err){
      chatHistory[loadingIndex]={role:'assistant',text:`I couldn't complete that request: ${err.message}`,meta:'Assistant error'};
    }finally{
      if(send) send.disabled=false; renderChat(); if(form) form.classList.remove('ai-loading');
    }
  }

  async function ensureAiDrawer(app){
    if(!qs('.ai-drawer',app)){
      const drawer=document.createElement('aside'); drawer.className='ai-drawer';
      drawer.innerHTML=`<div class="ai-header"><div class="ai-brandmark">✦</div><div class="ai-title"><strong>Crick AI</strong><small id="aiStatus">Cricket knowledge · Coaching · App help</small></div><button class="ai-collapse" id="aiCollapse" title="Collapse Crick AI">›</button></div><div class="ai-context" id="aiContext"></div><div class="ai-messages" id="aiMessages"></div><div class="ai-suggestions"><button data-ai-prompt="How do I analyze a specific shot?">Analyze a shot</button><button data-ai-prompt="What should I look for in a batter's head position?">Head position</button><button data-ai-prompt="What does Quick Review do?">Quick Review</button></div><form class="ai-form" id="aiForm"><div class="ai-input-wrap"><textarea id="aiInput" rows="2" placeholder="Ask anything about cricket or CrickAnalysis..."></textarea><button class="ai-send" id="aiSend" type="submit" aria-label="Send">↑</button></div><div class="ai-footnote" id="aiFootnote">App help is available now.</div></form>`;
      app.appendChild(drawer);
      qs('#aiCollapse',drawer).onclick=()=>toggleAi(app);
      qs('#aiForm',drawer).onsubmit=e=>{e.preventDefault();sendAiMessage(qs('#aiInput',drawer).value)};
      qs('#aiInput',drawer).onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendAiMessage(e.currentTarget.value)}};
      qsa('[data-ai-prompt]',drawer).forEach(b=>b.onclick=()=>sendAiMessage(b.dataset.aiPrompt));
      renderChat();
    }
    const cfg=await loadConfig();
    const status=qs('#aiStatus'); if(status) status.textContent=cfg.ai_configured?'Cricket knowledge · Web search · App help':'App help active · General cricket AI awaiting key';
    const foot=qs('#aiFootnote'); if(foot) foot.textContent=cfg.ai_configured?'General cricket Q&A and web search are active.':'CrickAnalysis help works now; server AI key enables general cricket Q&A.';
    const ctx=qs('#aiContext'); if(ctx) ctx.textContent=`Context: ${contextLabel()}`;
  }

  function toggleAi(app){
    app.classList.toggle('ai-collapsed');
    localStorage.setItem('crick-ai-collapsed',app.classList.contains('ai-collapsed')?'1':'0');
    updateTopChip(app);
  }

  function updateTopChip(app){
    const chip=qs('.top-chip',app); if(!chip) return;
    chip.innerHTML='✦ <span>Crick AI</span>';
    chip.title=app.classList.contains('ai-collapsed')?'Open Crick AI':'Collapse Crick AI';
    chip.classList.toggle('ai-active',!app.classList.contains('ai-collapsed'));
    chip.onclick=()=>toggleAi(app);
  }

  function ensureNavCollapse(app){
    const sidebar=qs('.sidebar',app); if(!sidebar) return;
    qsa('.nav button',sidebar).forEach(b=>{const label=qs('b',b)?.textContent||'';if(label)b.title=label});
    if(!qs('.sidebar-collapse',sidebar)){
      const btn=document.createElement('button'); btn.className='sidebar-collapse'; btn.title='Collapse navigation'; btn.textContent='‹';
      btn.onclick=()=>{app.classList.toggle('nav-collapsed');localStorage.setItem('crick-nav-collapsed',app.classList.contains('nav-collapsed')?'1':'0');btn.textContent=app.classList.contains('nav-collapsed')?'›':'‹';btn.title=app.classList.contains('nav-collapsed')?'Expand navigation':'Collapse navigation'};
      sidebar.appendChild(btn);
    }
    const btn=qs('.sidebar-collapse',sidebar); if(btn) btn.textContent=app.classList.contains('nav-collapsed')?'›':'‹';
  }

  function referenceCard(r){
    const initials=r.name.split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase();
    return `<a class="reference-card" href="${r.url}" target="_blank" rel="noopener noreferrer"><div class="reference-card-top"><span class="reference-icon">${initials}</span><span class="reference-open">↗</span></div><h3>${r.name}</h3><p>${r.desc}</p><div class="reference-tags">${r.tags.map(t=>`<span>${t}</span>`).join('')}</div></a>`;
  }

  function renderIntegrations(){
    if(currentPage()!=='integrations') return;
    const main=qs('.main'); if(!main || qs('#referenceLibrary',main)) return;
    const top=qs('.topbar',main); qsa(':scope > *',main).forEach(child=>{if(child!==top)child.remove()});
    const wrapper=document.createElement('div'); wrapper.id='referenceLibrary';
    wrapper.innerHTML=`<section class="page-head"><div><h1>Integrations & References</h1><p>Handy reference library while CrickAnalysis grows into the full product.</p></div></section><div class="reference-intro"><div class="warning"><b>Reference links:</b> these cards open the external products for research and comparison. They are not presented as live technical integrations.</div></div><div class="integration-section-title"><h2>Video, coaching & analysis tools</h2><p>Quick access to the products we are benchmarking or using as adjacent references.</p></div><section class="reference-grid">${REFERENCES.map(referenceCard).join('')}</section><div class="integration-section-title"><h2>Connected data sources</h2><p>CricClubs player lookup is available under Players. A true inline data import will require official API access.</p></div><article class="panel"><div class="panel-head"><div><h2>CricClubs</h2><p>Player statistics and profile lookup foundation.</p></div><button class="primary" id="goPlayers">Open Players →</button></div></article>`;
    main.appendChild(wrapper); qs('#goPlayers',wrapper).onclick=()=>navigate('players');
  }

  function enhancePlayers(){
    if(currentPage()!=='players') return;
    const grid=qs('.players-grid'); if(!grid || qs('#cricclubsPanel')) return;
    const panel=document.createElement('section'); panel.id='cricclubsPanel'; panel.className='cricclubs-panel';
    panel.innerHTML=`<div class="cricclubs-head"><div><strong>CricClubs Player Lookup</strong><p>Search the public CricClubs web presence by full name or CC Player ID. This is the MVP lookup bridge; we will replace it with an inline profile/stat import when official API access is available.</p></div><span class="bridge-badge">PUBLIC LOOKUP BRIDGE</span></div><form class="cricclubs-form" id="cricclubsForm"><select id="cricclubsType"><option value="name">Full name</option><option value="id">CC Player ID</option></select><input id="cricclubsQuery" required placeholder="Enter full player name"/><button type="submit">Search CricClubs ↗</button><a href="https://cricclubs.com/" target="_blank" rel="noopener">Open CricClubs</a></form><p class="cricclubs-note">Search opens in a new tab and is restricted to CricClubs pages. No data is imported into CrickAnalysis yet.</p>`;
    grid.parentNode.insertBefore(panel,grid);
    const type=qs('#cricclubsType',panel), input=qs('#cricclubsQuery',panel);
    type.onchange=()=>input.placeholder=type.value==='id'?'Enter CC Player ID':'Enter full player name';
    qs('#cricclubsForm',panel).onsubmit=e=>{e.preventDefault();const q=input.value.trim();if(!q)return;const search=type.value==='id'?`site:cricclubs.com "${q}" "CC Player ID"`:`site:cricclubs.com "${q}" cricket player`;window.open(`https://www.google.com/search?q=${encodeURIComponent(search)}`,'_blank','noopener')};
  }

  function formatBytes(bytes){
    if(!Number.isFinite(bytes)) return '';
    if(bytes>=1024*1024*1024)return `${(bytes/1024/1024/1024).toFixed(2)} GB`;
    return `${(bytes/1024/1024).toFixed(1)} MB`;
  }

  function captureFrames(video, strip){
    if(!video.duration || !Number.isFinite(video.duration)) return;
    const times=[.12,.38,.64,.88].map(p=>Math.max(0,Math.min(video.duration-.05,video.duration*p)));
    strip.innerHTML='';
    let index=0;
    const original=video.currentTime;
    const captureNext=()=>{
      if(index>=times.length){video.currentTime=original||0;return;}
      const t=times[index];
      const onSeek=()=>{
        video.removeEventListener('seeked',onSeek);
        const canvas=document.createElement('canvas');canvas.width=320;canvas.height=Math.max(180,Math.round(320*(video.videoHeight||9)/(video.videoWidth||16)));
        const ctx=canvas.getContext('2d');try{ctx.drawImage(video,0,0,canvas.width,canvas.height)}catch(_){ }
        const fig=document.createElement('figure');const img=document.createElement('img');img.src=canvas.toDataURL('image/jpeg',.72);const cap=document.createElement('figcaption');cap.textContent=`Preview ${index+1} · ${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`;fig.append(img,cap);strip.appendChild(fig);index++;captureNext();
      };
      video.addEventListener('seeked',onSeek,{once:true});video.currentTime=t;
    };
    captureNext();
  }

  function enhanceUpload(){
    if(currentPage()!=='upload') return;
    const card=qs('.upload-card'); if(!card || card.closest('.upload-workspace-v3')) return;
    const workspace=document.createElement('section');workspace.className='upload-workspace-v3';
    workspace.innerHTML=`<div class="upload-left"></div><div class="upload-right"><section class="upload-preview-panel"><div class="upload-preview-head"><div><strong>Video preview & processing</strong><small>Preview locally before uploading. Server progress will appear here during processing.</small></div><span class="upload-file-chip" id="uploadFileChip">No video selected</span></div><div class="local-video-wrap" id="localVideoWrap"><div class="upload-preview-empty" id="uploadPreviewEmpty"><strong>Your video will appear here</strong><span>Select a file on the left. You can verify the footage immediately before sending it to CrickAnalysis.</span></div><video id="localUploadVideo" controls preload="metadata" class="hidden"></video></div><div class="upload-live-status"><span id="uploadMirrorText">Waiting for video selection</span><div class="mini-track"><i id="uploadMirrorBar"></i></div></div><div class="local-previews"><div class="local-previews-head"><strong>Quick local previews</strong><span>No server analysis required</span></div><div class="local-preview-strip" id="localPreviewStrip"><div class="empty" style="grid-column:1/-1;padding:18px"><strong>No previews yet</strong>Select a video to generate a few local reference frames.</div></div></div></section></div>`;
    card.parentNode.insertBefore(workspace,card);qs('.upload-left',workspace).appendChild(card);
    const file=qs('#videoFile',card), video=qs('#localUploadVideo',workspace), empty=qs('#uploadPreviewEmpty',workspace), chip=qs('#uploadFileChip',workspace), strip=qs('#localPreviewStrip',workspace);
    if(file){
      file.addEventListener('change',()=>{
        const f=file.files?.[0];if(!f)return;
        if(uploadObjectUrl)URL.revokeObjectURL(uploadObjectUrl);uploadObjectUrl=URL.createObjectURL(f);
        video.src=uploadObjectUrl;video.classList.remove('hidden');empty.classList.add('hidden');chip.textContent=`${f.name} · ${formatBytes(f.size)}`;
        qs('#uploadMirrorText',workspace).textContent='Video selected — ready to upload';qs('#uploadMirrorBar',workspace).style.width='0%';
        video.onloadedmetadata=()=>captureFrames(video,strip);
      });
    }
    const status=qs('#uploadStatus',card), bar=qs('#progress div',card), mirror=qs('#uploadMirrorText',workspace), mirrorBar=qs('#uploadMirrorBar',workspace);
    if(status){new MutationObserver(()=>{if(status.textContent.trim())mirror.textContent=status.textContent.trim()}).observe(status,{childList:true,subtree:true,characterData:true})}
    if(bar){new MutationObserver(()=>{mirrorBar.style.width=bar.style.width||'0%';if(bar.style.background)mirrorBar.style.background=bar.style.background}).observe(bar,{attributes:true,attributeFilter:['style']})}
  }

  function enhanceShell(){
    const app=qs('.app'); if(!app) return;
    if(localStorage.getItem('crick-nav-collapsed')==='1') app.classList.add('nav-collapsed');
    if(localStorage.getItem('crick-ai-collapsed')==='1') app.classList.add('ai-collapsed');
    ensureNavCollapse(app); ensureAiDrawer(app); updateTopChip(app);
    renderIntegrations(); enhancePlayers(); enhanceUpload();
    const ctx=qs('#aiContext'); if(ctx)ctx.textContent=`Context: ${contextLabel()}`;
  }

  function scheduleEnhance(){clearTimeout(enhanceTimer);enhanceTimer=setTimeout(enhanceShell,30)}
  const observer=new MutationObserver(scheduleEnhance);observer.observe(document.documentElement,{childList:true,subtree:true});
  window.addEventListener('hashchange',()=>setTimeout(enhanceShell,40));
  setInterval(()=>{const ctx=qs('#aiContext');if(ctx)ctx.textContent=`Context: ${contextLabel()}`},1000);
  enhanceShell();
})();
