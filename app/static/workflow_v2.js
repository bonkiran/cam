(() => {
  let configCache = null;

  async function getConfig() {
    if (configCache) return configCache;
    const res = await fetch('/api/config');
    if (!res.ok) throw new Error('Could not load application configuration.');
    configCache = await res.json();
    return configCache;
  }

  function fmtBytes(bytes) {
    if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  function modeMarkup() {
    return `<div class="workflow-modes" id="workflowModes"><div class="workflow-title"><strong>What would you like to do with this video?</strong><span>Quick Review is recommended for normal uploads.</span></div><div class="mode-grid"><label class="mode-card"><input type="radio" name="analysis_mode" value="quick" checked><span class="mode-name">Quick Review <b>Recommended</b></span><small>Fast metadata + a small set of preview frames. No full-video motion scan.</small></label><label class="mode-card"><input type="radio" name="analysis_mode" value="shot"><span class="mode-name">Analyze Specific Shot</span><small>Prepare quickly, then seek to the exact shot for slow-motion, frame and evidence review.</small></label><label class="mode-card heavy"><input type="radio" name="analysis_mode" value="full"><span class="mode-name">Full Video Scan <b>Slower</b></span><small>Optional whole-video motion scan. Use only when you want candidate moments across the entire video.</small></label></div></div>`;
  }

  async function enhanceUploadForm() {
    const form = document.querySelector('#uploadForm');
    if (!form || form.dataset.workflowV2 === '1') return;
    form.dataset.workflowV2 = '1';
    const dropzone = form.querySelector('.dropzone');
    if (dropzone) dropzone.insertAdjacentHTML('beforebegin', modeMarkup());
    try {
      const cfg = await getConfig();
      const note = form.querySelector('.dropzone .note');
      if (note) note.textContent = `MP4, MOV, M4V, AVI, WebM or MKV · current server limit ${cfg.max_upload_label}`;
    } catch (_) {}
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.textContent = 'Upload & Open Review';
    form.addEventListener('submit', customUpload, true);
  }

  async function customUpload(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    const form = event.currentTarget;
    const input = form.querySelector('#videoFile');
    const file = input && input.files ? input.files[0] : null;
    if (!file) return;
    let cfg;
    try { cfg = await getConfig(); } catch (err) { toast(err.message); return; }
    const progress = form.querySelector('#progress');
    const bar = progress ? progress.querySelector('div') : null;
    const status = form.querySelector('#uploadStatus');
    const submit = form.querySelector('button[type="submit"]');
    const mode = form.querySelector('input[name="analysis_mode"]:checked')?.value || 'quick';
    const modeLabel = cfg.analysis_modes?.[mode]?.label || mode;
    if (file.size > cfg.max_upload_bytes) {
      if (progress) progress.classList.remove('hidden');
      if (bar) { bar.style.width = '100%'; bar.style.background = '#d84b4b'; }
      const message = `${fmtBytes(file.size)} exceeds the current ${cfg.max_upload_label} server upload limit.`;
      if (status) status.textContent = message;
      toast(message);
      return;
    }
    const data = new FormData(form);
    data.set('analysis_mode', mode);
    if (progress) progress.classList.remove('hidden');
    if (bar) { bar.style.width = '0%'; bar.style.background = ''; }
    if (submit) submit.disabled = true;
    if (status) status.textContent = `Uploading ${file.name} (${fmtBytes(file.size)}) for ${modeLabel}…`;
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/videos');
    xhr.upload.onprogress = ev => { if (!ev.lengthComputable) return; const pct = Math.round((ev.loaded / ev.total) * 100); if (bar) bar.style.width = `${pct}%`; if (status) status.textContent = `Uploading ${file.name}… ${pct}%`; };
    xhr.upload.onload = () => { if (status) status.textContent = 'Upload transferred. Server is accepting the video…'; };
    xhr.onerror = () => { if (bar) bar.style.background = '#d84b4b'; if (submit) submit.disabled = false; const message = 'Upload failed because the connection was interrupted.'; if (status) status.textContent = message; toast(message); };
    xhr.onload = () => {
      if (submit) submit.disabled = false;
      if (xhr.status >= 200 && xhr.status < 300) {
        const video = JSON.parse(xhr.responseText);
        if (bar) bar.style.width = '100%';
        if (status) status.textContent = `${modeLabel} accepted. Opening the review page…`;
        toast(`${modeLabel} started.`);
        setTimeout(() => navigate(`analysis?id=${video.id}`), 250);
        return;
      }
      if (bar) { bar.style.width = '100%'; bar.style.background = '#d84b4b'; }
      let detail = `Upload failed (${xhr.status}).`;
      try { const body = JSON.parse(xhr.responseText); if (body.detail) detail = body.detail; } catch (_) {}
      if (status) status.textContent = detail;
      toast(detail);
    };
    xhr.send(data);
  }

  function analysisIdFromHash() { const match = location.hash.match(/^#analysis\?id=(\d+)/); return match ? Number(match[1]) : null; }
  function progressMarkup(video) {
    const pct = Math.max(0, Math.min(100, Number(video.progress_percent || 0)));
    return `<div class="workflow-progress" id="workflowProgress"><div class="workflow-progress-head"><strong>${video.progress_stage || 'Preparing video'}</strong><span>${pct}%</span></div><div class="workflow-progress-track"><div style="width:${pct}%"></div></div><p>${video.analysis_mode === 'full' ? 'Full Video Scan is the heavier option. You can cancel it without restarting the server.' : 'This lightweight preparation avoids the old full-video scan.'}</p>${video.status === 'uploaded' || video.status === 'processing' ? '<button class="danger" id="cancelAnalysis">Cancel Analysis</button>' : ''}</div>`;
  }
  async function cancelAnalysis(videoId) {
    const button = document.querySelector('#cancelAnalysis');
    if (button) { button.disabled = true; button.textContent = 'Cancelling…'; }
    try { const res = await fetch(`/api/videos/${videoId}/cancel`, { method: 'POST' }); if (!res.ok) throw new Error('Could not cancel analysis.'); toast('Analysis cancelled.'); }
    catch (err) { toast(err.message); if (button) { button.disabled = false; button.textContent = 'Cancel Analysis'; } }
  }
  function modeLabel(mode) { return {quick:'Quick Review',shot:'Specific Shot Review',full:'Full Video Scan'}[mode] || mode; }
  function addReadyBanner(video) {
    const layout = document.querySelector('.analysis-layout');
    if (!layout || document.querySelector('#workflowReadyBanner')) return;
    const banner = document.createElement('div');
    banner.id = 'workflowReadyBanner'; banner.className = 'workflow-ready-banner';
    banner.innerHTML = `<div><strong>${modeLabel(video.analysis_mode)} ready</strong><p>${video.analysis_mode === 'full' ? 'Full-video motion candidates and timeline frames are available.' : 'No heavy whole-video scan was run. Play the video, use slow motion/frame stepping, and extract evidence around the shot you care about.'}</p></div>${video.analysis_mode !== 'full' ? '<button class="secondary" id="runFullScan">Run Full Video Scan</button>' : ''}`;
    layout.parentNode.insertBefore(banner, layout);
    const fullButton = banner.querySelector('#runFullScan');
    if (fullButton) fullButton.onclick = async () => { if (!confirm('Full Video Scan can take much longer on a large video. Start it now?')) return; fullButton.disabled = true; fullButton.textContent = 'Starting…'; try { const res = await fetch(`/api/videos/${video.id}/reanalyze?mode=full`, { method:'POST' }); if (!res.ok) throw new Error('Could not start Full Video Scan.'); toast('Full Video Scan started.'); setTimeout(() => location.reload(), 250); } catch (err) { toast(err.message); fullButton.disabled = false; fullButton.textContent = 'Run Full Video Scan'; } };
    if (video.analysis_mode !== 'full') {
      document.querySelectorAll('.panel').forEach(panel => {
        const heading = panel.querySelector('h2');
        if (heading && heading.textContent.trim() === 'Motion Timeline') panel.classList.add('hidden');
        if (heading && heading.textContent.trim() === 'Generated Frames') {
          const p = panel.querySelector('.panel-head p'); if (p) p.textContent = 'Lightweight preview frames. Click a frame to seek the video.';
          const candidateOnly = panel.querySelector('#candidateOnly')?.closest('label'); if (candidateOnly) candidateOnly.classList.add('hidden');
        }
      });
    }
  }
  async function refreshAnalysisEnhancements() {
    const videoId = analysisIdFromHash(); if (!videoId) return;
    try {
      const res = await fetch(`/api/videos/${videoId}`, { cache:'no-store' }); if (!res.ok) return; const video = await res.json();
      if (video.status === 'uploaded' || video.status === 'processing') {
        const empty = document.querySelector('.panel .empty');
        if (empty) { let box = document.querySelector('#workflowProgress'); if (!box) { empty.insertAdjacentHTML('beforeend', progressMarkup(video)); } else { box.outerHTML = progressMarkup(video); } const cancelButton = document.querySelector('#cancelAnalysis'); if (cancelButton) cancelButton.onclick = () => cancelAnalysis(videoId); }
      } else if (video.status === 'cancelled') {
        const empty = document.querySelector('.panel .empty'); if (empty) empty.innerHTML = '<strong>Analysis cancelled</strong><p>The video remains available. You can return to My Analyses or re-run a lightweight review later.</p>';
      } else if (video.status === 'failed') {
        const empty = document.querySelector('.panel .empty'); if (empty && video.error) empty.innerHTML = `<strong>Analysis failed</strong><p>${video.error}</p>`;
      } else if (video.status === 'complete') addReadyBanner(video);
    } catch (_) {}
  }
  const observer = new MutationObserver(() => { enhanceUploadForm(); refreshAnalysisEnhancements(); });
  observer.observe(document.documentElement, { childList:true, subtree:true });
  window.addEventListener('hashchange', () => setTimeout(refreshAnalysisEnhancements, 50));
  setInterval(refreshAnalysisEnhancements, 1000);
  enhanceUploadForm(); refreshAnalysisEnhancements();
})();
