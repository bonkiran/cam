(() => {
  const qs = (selector, root = document) => root.querySelector(selector);
  const stateByVideo = new Map();
  let configPromise = null;
  let enhanceTimer = null;

  function currentVideoId() {
    const raw = location.hash.replace(/^#/, "");
    const [page, query = ""] = raw.split("?");
    if (page !== "analysis") return null;
    const id = Number(new URLSearchParams(query).get("id"));
    return Number.isFinite(id) && id > 0 ? id : null;
  }

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, options);
    let body = {};
    try { body = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  }

  function getConfig() {
    if (!configPromise) {
      configPromise = jsonFetch("/api/biomechanics/config").catch(error => ({
        configured: false,
        message: `Biomechanics service unavailable: ${error.message}`,
        grading: false,
      }));
    }
    return configPromise;
  }

  function fmtTime(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    const min = Math.floor(value / 60);
    return `${min}:${String((value % 60).toFixed(2)).padStart(5, "0")}`;
  }

  function formatMetric(metrics, primary, ratioKey, kind) {
    const value = metrics?.[primary];
    if (Number.isFinite(value)) {
      return kind === "angle" ? `${value.toFixed(1)}°` : `${value.toFixed(1)} cm`;
    }
    const ratio = metrics?.[ratioKey];
    if (Number.isFinite(ratio)) return `${(ratio * 100).toFixed(1)}% height`;
    return "—";
  }

  function panelHtml(config) {
    return `
      <div class="biomech-head">
        <div>
          <div class="biomech-title-row">
            <h2>Biomechanics Scan</h2>
            <span class="biomech-experimental">EXPERIMENTAL</span>
          </div>
          <p>Short-shot body geometry using a PoseForge-compatible SAM-3D pose engine.</p>
        </div>
        <span class="biomech-engine ${config.configured ? "connected" : "offline"}">
          ${config.configured ? "● POSE ENGINE CONNECTED" : "○ POSE ENGINE NOT CONNECTED"}
        </span>
      </div>
      <div class="biomech-truth">
        Geometry only for this spike. CrickAnalysis does <b>not</b> label these values Elite/Good/Poor yet.
      </div>
      <div class="biomech-controls">
        <div class="biomech-playhead">
          <span>Shot center</span>
          <strong id="biomechCenter">0:00.00</strong>
          <small>Uses the current video playhead</small>
        </div>
        <label>Window
          <select id="biomechWindow">
            <option value="4">4 sec</option>
            <option value="6" selected>6 sec</option>
            <option value="8">8 sec</option>
          </select>
        </label>
        <label>Batting
          <select id="biomechHandedness">
            <option value="right" selected>Right-handed</option>
            <option value="left">Left-handed</option>
          </select>
        </label>
        <label>Camera
          <select id="biomechView">
            <option value="other" selected>Other / unknown</option>
            <option value="front">Front view</option>
            <option value="side">Side view</option>
          </select>
        </label>
        <label>Height <span>(optional)</span>
          <input id="biomechHeight" type="number" min="100" max="230" step="1" placeholder="cm" />
        </label>
        <button class="primary biomech-run" id="biomechRun" ${config.configured ? "" : "disabled"}>
          Run Biomechanics Scan
        </button>
      </div>
      <p class="biomech-engine-note" id="biomechEngineNote">${config.message || ""}</p>
      <div class="biomech-status hidden" id="biomechStatus">
        <div>
          <strong id="biomechStage">Queued</strong>
          <span id="biomechStatusMeta"></span>
        </div>
        <div class="biomech-progress"><i id="biomechProgress"></i></div>
      </div>
      <div class="biomech-result hidden" id="biomechResult">
        <div class="biomech-skeleton-card">
          <div class="biomech-subhead">
            <div><strong>Pose skeleton</strong><span id="biomechFrameLabel"></span></div>
            <span id="biomechTrackLabel"></span>
          </div>
          <canvas id="biomechCanvas" width="720" height="520"></canvas>
          <small>3D joint coordinates projected into a coaching view. Video and pose follow the same playhead.</small>
        </div>
        <div class="biomech-metrics">
          <div class="biomech-metric"><span>Front knee angle</span><strong id="metricKnee">—</strong><small>Leading hip → knee → ankle</small></div>
          <div class="biomech-metric"><span>Trunk lean</span><strong id="metricTrunk">—</strong><small>Torso angle from vertical</small></div>
          <div class="biomech-metric"><span>Stance width</span><strong id="metricStance">—</strong><small>Feet separation; cm if height supplied</small></div>
          <div class="biomech-metric"><span>Head movement</span><strong id="metricHead">—</strong><small>Horizontal displacement from scan start</small></div>
          <div class="biomech-evidence-note" id="biomechEvidenceNote"></div>
        </div>
      </div>
    `;
  }

  async function loadLatest(videoId, panel) {
    try {
      const runs = await jsonFetch(`/api/videos/${videoId}/biomechanics`);
      if (!Array.isArray(runs) || !runs.length) return;
      const latest = runs[0];
      stateByVideo.set(videoId, { run: latest, result: null, poll: null });
      renderRun(panel, videoId, latest);
      if (latest.status === "queued" || latest.status === "processing") pollRun(panel, videoId, latest.id);
      if (latest.status === "complete") {
        const full = await jsonFetch(`/api/biomechanics/${latest.id}`);
        renderRun(panel, videoId, full);
      }
    } catch (_) {}
  }

  function setStatus(panel, run) {
    const box = qs("#biomechStatus", panel);
    const stage = qs("#biomechStage", panel);
    const meta = qs("#biomechStatusMeta", panel);
    const progress = qs("#biomechProgress", panel);
    if (!box) return;
    box.classList.remove("hidden");
    stage.textContent = run.progress_stage || run.status || "Working";
    const details = [];
    if (Number.isFinite(run.start_timestamp) && Number.isFinite(run.end_timestamp)) {
      details.push(`${fmtTime(run.start_timestamp)}–${fmtTime(run.end_timestamp)}`);
    }
    if (run.error) details.push(run.error);
    meta.textContent = details.join(" · ");
    const pct = Math.max(0, Math.min(100, Number(run.progress_percent) || 0));
    progress.style.width = `${pct}%`;
    box.classList.toggle("failed", run.status === "failed");
  }

  function renderRun(panel, videoId, run) {
    const existing = stateByVideo.get(videoId) || {};
    const result = run.result || existing.result || null;
    stateByVideo.set(videoId, { ...existing, run, result });
    setStatus(panel, run);
    const runButton = qs("#biomechRun", panel);
    if (runButton) {
      const busy = run.status === "queued" || run.status === "processing";
      runButton.disabled = busy || runButton.dataset.engine !== "connected";
      runButton.textContent = busy ? "Biomechanics Scan Running…" : "Run Biomechanics Scan";
    }
    if (run.status === "complete" && run.result) {
      stateByVideo.set(videoId, { ...stateByVideo.get(videoId), result: run.result });
      qs("#biomechResult", panel)?.classList.remove("hidden");
      updateFromPlayhead(panel, videoId);
    }
  }

  function pollRun(panel, videoId, runId) {
    const existing = stateByVideo.get(videoId) || {};
    if (existing.poll) clearTimeout(existing.poll);
    const tick = async () => {
      if (!document.body.contains(panel) || currentVideoId() !== videoId) return;
      try {
        const run = await jsonFetch(`/api/biomechanics/${runId}`);
        renderRun(panel, videoId, run);
        if (run.status === "queued" || run.status === "processing") {
          const timer = setTimeout(tick, 1600);
          stateByVideo.set(videoId, { ...stateByVideo.get(videoId), poll: timer });
        }
      } catch (error) {
        const stage = qs("#biomechStage", panel);
        if (stage) stage.textContent = error.message;
      }
    };
    tick();
  }

  function nearestFrame(result, timestamp) {
    const frames = result?.frames || [];
    if (!frames.length) return null;
    let best = frames[0];
    let bestDelta = Math.abs(Number(best.timestamp) - timestamp);
    for (let i = 1; i < frames.length; i++) {
      const delta = Math.abs(Number(frames[i].timestamp) - timestamp);
      if (delta < bestDelta) {
        best = frames[i];
        bestDelta = delta;
      }
    }
    return best;
  }

  function drawSkeleton(canvas, result, frame) {
    if (!canvas || !frame?.skeleton) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const skeleton = frame.skeleton;
    const useSide = result.camera_view === "side";
    const projectRaw = point => point ? [useSide ? point[2] : point[0], point[1]] : null;
    const projected = Object.fromEntries(
      Object.entries(skeleton).map(([key, point]) => [key, projectRaw(point)])
    );
    const values = Object.values(projected).filter(Boolean);
    if (!values.length) return;

    const xs = values.map(p => p[0]);
    const ys = values.map(p => p[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const spanX = Math.max(0.001, maxX - minX);
    const spanY = Math.max(0.001, maxY - minY);
    const padding = 56;
    const scale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY);
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    const toCanvas = point => [
      width / 2 + (point[0] - centerX) * scale,
      height / 2 - (point[1] - centerY) * scale,
    ];

    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = 7;
    ctx.strokeStyle = "#d8f0df";
    (result.bones || []).forEach(([a, b]) => {
      const pa = projected[a], pb = projected[b];
      if (!pa || !pb) return;
      const [x1, y1] = toCanvas(pa);
      const [x2, y2] = toCanvas(pb);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    });

    Object.entries(projected).forEach(([key, point]) => {
      if (!point) return;
      const [x, y] = toCanvas(point);
      const leading = key.startsWith("lead_");
      const important = key === "head" || key === "pelvis";
      ctx.beginPath();
      ctx.arc(x, y, important ? 9 : 7, 0, Math.PI * 2);
      ctx.fillStyle = leading ? "#64d98a" : "#f4f7f5";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#153e2a";
      ctx.stroke();
    });
  }

  function updateFromPlayhead(panel, videoId) {
    const video = qs("#player");
    const saved = stateByVideo.get(videoId);
    const result = saved?.result;
    if (!video || !result?.frames?.length) return;

    const timestamp = Number(video.currentTime) || 0;
    const frame = nearestFrame(result, timestamp);
    if (!frame) return;
    const inside = timestamp >= Number(result.start_timestamp) - 0.1 && timestamp <= Number(result.end_timestamp) + 0.1;

    qs("#biomechFrameLabel", panel).textContent = `${fmtTime(frame.timestamp)} · pose frame ${frame.pose_frame_index}`;
    qs("#biomechTrackLabel", panel).textContent = `${result.person_id} · ${result.detected_people?.length || 1} track(s)`;
    qs("#metricKnee", panel).textContent = formatMetric(frame.metrics, "front_knee_angle_deg", "", "angle");
    qs("#metricTrunk", panel).textContent = formatMetric(frame.metrics, "trunk_lean_deg", "", "angle");
    qs("#metricStance", panel).textContent = formatMetric(frame.metrics, "stance_width_cm", "stance_width_ratio", "distance");
    qs("#metricHead", panel).textContent = formatMetric(frame.metrics, "head_displacement_cm", "head_displacement_ratio", "distance");
    qs("#biomechEvidenceNote", panel).textContent = inside
      ? `Synchronized to the source video at ${fmtTime(timestamp)}. Auto-selected the longest available person track for this first spike.`
      : `The current playhead is outside this scan (${fmtTime(result.start_timestamp)}–${fmtTime(result.end_timestamp)}). Showing the nearest pose frame.`;
    drawSkeleton(qs("#biomechCanvas", panel), result, frame);
  }

  async function runScan(panel, videoId) {
    const video = qs("#player");
    if (!video) return;
    const heightRaw = qs("#biomechHeight", panel)?.value.trim();
    const payload = {
      center_timestamp: Number(video.currentTime) || 0,
      window_seconds: Number(qs("#biomechWindow", panel)?.value || 6),
      handedness: qs("#biomechHandedness", panel)?.value || "right",
      camera_view: qs("#biomechView", panel)?.value || "other",
      height_cm: heightRaw ? Number(heightRaw) : null,
    };
    const button = qs("#biomechRun", panel);
    button.disabled = true;
    button.textContent = "Starting Biomechanics Scan…";
    try {
      const run = await jsonFetch(`/api/videos/${videoId}/biomechanics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      renderRun(panel, videoId, run);
      pollRun(panel, videoId, run.id);
    } catch (error) {
      button.disabled = false;
      button.textContent = "Run Biomechanics Scan";
      const note = qs("#biomechEngineNote", panel);
      if (note) note.textContent = error.message;
    }
  }

  async function enhance() {
    clearTimeout(enhanceTimer);
    enhanceTimer = setTimeout(async () => {
      const videoId = currentVideoId();
      const video = qs("#player");
      if (!videoId || !video) return;
      if (qs("#biomechanicsPanel")) return;

      const config = await getConfig();
      if (currentVideoId() !== videoId || !qs("#player")) return;
      const hostPanel = video.closest(".panel");
      if (!hostPanel) return;

      const panel = document.createElement("article");
      panel.id = "biomechanicsPanel";
      panel.className = "panel biomech-panel";
      panel.innerHTML = panelHtml(config);
      hostPanel.insertAdjacentElement("afterend", panel);

      const runButton = qs("#biomechRun", panel);
      runButton.dataset.engine = config.configured ? "connected" : "offline";
      runButton.disabled = !config.configured;
      runButton.onclick = () => runScan(panel, videoId);

      const center = qs("#biomechCenter", panel);
      const sync = () => {
        if (center) center.textContent = fmtTime(video.currentTime);
        updateFromPlayhead(panel, videoId);
      };
      video.addEventListener("timeupdate", sync);
      video.addEventListener("seeked", sync);
      sync();

      loadLatest(videoId, panel);
    }, 70);
  }

  window.addEventListener("hashchange", enhance);
  const observer = new MutationObserver(enhance);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  enhance();
})();
