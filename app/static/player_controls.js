(() => {
  const SPEEDS = [0.1, 0.25, 0.5, 1];
  let loopState = null;

  function fmtSpeed(value){
    return value === 1 ? '1×' : `${value}×`;
  }

  function isStageFullscreen(stage){
    return document.fullscreenElement === stage || document.webkitFullscreenElement === stage;
  }

  function setFullscreenButton(stage, button){
    if(!button) return;
    button.textContent = isStageFullscreen(stage) ? '↙ Exit Full Screen' : '⛶ Coaching Full Screen';
    button.classList.toggle('active', isStageFullscreen(stage));
  }

  async function toggleStageFullscreen(stage, button){
    try{
      if(isStageFullscreen(stage)){
        if(document.exitFullscreen) await document.exitFullscreen();
        else if(document.webkitExitFullscreen) document.webkitExitFullscreen();
      }else{
        if(stage.requestFullscreen) await stage.requestFullscreen();
        else if(stage.webkitRequestFullscreen) stage.webkitRequestFullscreen();
      }
    }catch(err){
      console.error('Fullscreen failed', err);
    }finally{
      setFullscreenButton(stage, button);
    }
  }

  function setSpeed(player, speed, root){
    player.playbackRate = speed;
    root.querySelectorAll('[data-coach-speed]').forEach(btn => {
      btn.classList.toggle('active', Number(btn.dataset.coachSpeed) === speed);
    });
  }

  function clearLoop(root){
    loopState = null;
    const btn = root.querySelector('#coachLoop');
    if(btn){
      btn.classList.remove('active');
      btn.textContent = '↻ Loop ±2s';
    }
  }

  function toggleLoop(player, root){
    const btn = root.querySelector('#coachLoop');
    if(loopState){
      clearLoop(root);
      return;
    }
    const center = player.currentTime || 0;
    loopState = {
      start: Math.max(0, center - 2),
      end: Math.min(player.duration || center + 2, center + 2)
    };
    btn.classList.add('active');
    btn.textContent = `↻ ${loopState.start.toFixed(1)}–${loopState.end.toFixed(1)}s`;
    player.currentTime = loopState.start;
    player.play().catch(()=>{});
  }

  function enhancePlayer(){
    const player = document.querySelector('#player');
    if(!player || player.dataset.coachEnhanced === '1') return;

    const stage = player.closest('.video-stage');
    const transport = stage?.querySelector('.transport');
    if(!stage || !transport) return;

    player.dataset.coachEnhanced = '1';
    transport.classList.add('coach-transport');

    // Where supported, hide the browser's video-only fullscreen button.
    // The app fullscreen button expands the entire stage including coaching controls.
    player.setAttribute('controlsList', 'nofullscreen noremoteplayback');

    const speedGroup = document.createElement('div');
    speedGroup.className = 'coach-control-group coach-speed-group';
    speedGroup.innerHTML = `<span class="coach-control-label">Slow motion</span>${SPEEDS.map(s =>
      `<button type="button" class="coach-btn ${s===1?'active':''}" data-coach-speed="${s}" title="Play at ${fmtSpeed(s)} speed">${fmtSpeed(s)}</button>`
    ).join('')}`;

    const reviewGroup = document.createElement('div');
    reviewGroup.className = 'coach-control-group';
    reviewGroup.innerHTML = `
      <button type="button" class="coach-btn" id="coachPlayPause">▶ Play</button>
      <button type="button" class="coach-btn" id="coachLoop" title="Loop two seconds before and after the current position">↻ Loop ±2s</button>
      <button type="button" class="coach-btn coach-primary" id="coachFullscreen">⛶ Coaching Full Screen</button>`;

    transport.prepend(reviewGroup);
    transport.prepend(speedGroup);

    const hint = document.createElement('div');
    hint.className = 'fullscreen-hint';
    hint.textContent = 'Use “Coaching Full Screen” to keep slow-motion, frame-step and evidence controls visible while fullscreen.';
    transport.appendChild(hint);

    const playPause = transport.querySelector('#coachPlayPause');
    const loopButton = transport.querySelector('#coachLoop');
    const fullscreenButton = transport.querySelector('#coachFullscreen');

    transport.querySelectorAll('[data-coach-speed]').forEach(btn => {
      btn.addEventListener('click', () => {
        setSpeed(player, Number(btn.dataset.coachSpeed), transport);
        if(player.paused) player.play().catch(()=>{});
      });
    });

    playPause.addEventListener('click', () => {
      if(player.paused) player.play().catch(()=>{});
      else player.pause();
    });

    player.addEventListener('play', () => playPause.textContent = '❚❚ Pause');
    player.addEventListener('pause', () => playPause.textContent = '▶ Play');
    player.addEventListener('ratechange', () => {
      const matching = SPEEDS.find(s => Math.abs(s - player.playbackRate) < 0.001);
      if(matching) setSpeed(player, matching, transport);
    });

    loopButton.addEventListener('click', () => toggleLoop(player, transport));
    player.addEventListener('timeupdate', () => {
      if(loopState && player.currentTime >= loopState.end){
        player.currentTime = loopState.start;
        player.play().catch(()=>{});
      }
    });
    player.addEventListener('seeking', () => {
      if(loopState && (player.currentTime < loopState.start - .1 || player.currentTime > loopState.end + .1)){
        clearLoop(transport);
      }
    });

    fullscreenButton.addEventListener('click', () => toggleStageFullscreen(stage, fullscreenButton));
    document.addEventListener('fullscreenchange', () => setFullscreenButton(stage, fullscreenButton));
    document.addEventListener('webkitfullscreenchange', () => setFullscreenButton(stage, fullscreenButton));

    setSpeed(player, 1, transport);
  }

  const observer = new MutationObserver(enhancePlayer);
  observer.observe(document.documentElement, {subtree:true, childList:true});
  document.addEventListener('DOMContentLoaded', enhancePlayer);
  enhancePlayer();
})();
