const CLOUD_UPLOAD_LIMIT_BYTES = 512 * 1024 * 1024;

// Replace the original upload handler with a cloud-aware version that keeps
// the user informed after the browser finishes sending the file and while the
// server validates it.
window.uploadVideo = function uploadVideoCloud(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const fileInput = document.querySelector('#videoFile');
  const file = fileInput && fileInput.files ? fileInput.files[0] : null;
  if (!file) return;

  const progress = document.querySelector('#progress');
  const bar = progress ? progress.querySelector('div') : null;
  const status = document.querySelector('#uploadStatus');

  if (file.size > CLOUD_UPLOAD_LIMIT_BYTES) {
    if (progress) progress.classList.remove('hidden');
    if (bar) {
      bar.style.width = '100%';
      bar.style.background = '#d84b4b';
    }
    const message = `Upload rejected before sending: ${fileSize(file.size)} exceeds the current 512 MB cloud-test limit.`;
    if (status) status.textContent = message;
    toast(message);
    return;
  }

  const fd = new FormData(form);
  if (progress) progress.classList.remove('hidden');
  if (bar) {
    bar.style.width = '0%';
    bar.style.background = '';
  }
  if (status) status.textContent = `Uploading ${file.name} (${fileSize(file.size)})…`;

  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/videos');

  xhr.upload.onprogress = ev => {
    if (ev.lengthComputable && bar) {
      const pct = Math.round((ev.loaded / ev.total) * 100);
      bar.style.width = `${pct}%`;
      if (status) status.textContent = `Uploading ${file.name} (${fileSize(file.size)})… ${pct}%`;
    }
  };

  xhr.upload.onload = () => {
    if (status) status.textContent = 'Upload transferred. Server is validating the file…';
  };

  xhr.onerror = () => {
    if (bar) bar.style.background = '#d84b4b';
    const message = 'Upload failed because the network connection was interrupted.';
    if (status) status.textContent = message;
    toast(message);
  };

  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      const v = JSON.parse(xhr.responseText);
      if (bar) bar.style.width = '100%';
      if (status) status.textContent = 'Upload accepted. Video analysis has started…';
      toast('Video uploaded. Processing frames now.');
      setTimeout(() => navigate(`analysis?id=${v.id}`), 500);
      return;
    }

    if (bar) {
      bar.style.width = '100%';
      bar.style.background = '#d84b4b';
    }

    let detail = `Upload failed (${xhr.status}).`;
    try {
      const data = JSON.parse(xhr.responseText);
      if (data.detail) detail = data.detail;
    } catch (_) {}

    if (xhr.status === 413) {
      detail = `Upload rejected: ${fileSize(file.size)} exceeds the current 512 MB cloud-test limit.`;
    }

    if (status) status.textContent = detail;
    toast(detail);
  };

  xhr.send(fd);
};

// The base app also runs locally with a larger default limit. Update the copy
// when this cloud helper is loaded so the Render UI does not advertise 2 GB.
const uploadCopyObserver = new MutationObserver(() => {
  document.querySelectorAll('.dropzone .note').forEach(note => {
    if (note.textContent.includes('local MVP limit 2 GB')) {
      note.textContent = 'MP4, MOV, M4V, AVI, WebM or MKV · Render cloud-test limit 512 MB';
    }
  });
});
uploadCopyObserver.observe(document.documentElement, { childList: true, subtree: true });
