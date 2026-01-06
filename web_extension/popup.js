(function(){
  const api = typeof chrome !== 'undefined' ? chrome : browser;
  const startBtn = document.getElementById('start');
  const stopBtn = document.getElementById('stop');
  const includeSystemEl = document.getElementById('includeSystem');
  const titleEl = document.getElementById('title');
  const statusEl = document.getElementById('status');

  let micStream = null, sysStream = null, mediaRecorder = null, chunks = [];

  async function getBaseUrl(){
    return new Promise(resolve => {
      api.storage.sync.get({ serverBase: 'http://localhost:8000' }, (res) => resolve(res.serverBase));
    });
  }

  async function getMic(){
    return navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  }
  async function getSystem(){
    try {
      const s = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
      const a = s.getAudioTracks();
      if (a && a.length) return s;
      s.getTracks().forEach(t=>t.stop());
      return null;
    } catch(e){ return null; }
  }

  function cleanup(){
    if (micStream) { micStream.getTracks().forEach(t=>t.stop()); micStream=null; }
    if (sysStream) { sysStream.getTracks().forEach(t=>t.stop()); sysStream=null; }
  }

  async function start(){
    startBtn.disabled = true; stopBtn.disabled = false;
    statusEl.textContent = 'Requesting media...';
    const includeSystem = includeSystemEl.checked;
    micStream = await getMic();
    if (includeSystem) sysStream = await getSystem();

    let target = null;
    if (sysStream){
      const ctx = new (window.AudioContext||window.webkitAudioContext)();
      const dest = ctx.createMediaStreamDestination();
      ctx.createMediaStreamSource(micStream).connect(dest);
      ctx.createMediaStreamSource(sysStream).connect(dest);
      target = dest.stream;
    } else {
      target = micStream;
    }

    chunks = [];
    let opts = { mimeType: 'audio/webm;codecs=opus' };
    if (!MediaRecorder.isTypeSupported(opts.mimeType)) opts = {};
    mediaRecorder = new MediaRecorder(target, opts);
    mediaRecorder.ondataavailable = e=>{ if (e.data && e.data.size>0) chunks.push(e.data); };
    mediaRecorder.onstop = async ()=>{
      statusEl.textContent = 'Stopping...';
      const blob = new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' });
      const defaultTitle = titleEl.value || `Recording_${new Date().toISOString().replace(/[:T]/g,'-').slice(0,19)}`;
      const fileName = defaultTitle + '.webm';
      const arrBuf = await blob.arrayBuffer();

      const base = await getBaseUrl();
      const dashboardUrl = base.replace(/\/$/, '') + '/dashboard/';

      // Find or open dashboard tab
      api.tabs.query({}, async (tabs)=>{
        let targetTab = tabs.find(t => t.url && t.url.startsWith(dashboardUrl));
        if (!targetTab){
          api.tabs.create({ url: dashboardUrl }, (tab)=> attachAndSubmitWhenReady(tab.id, arrBuf, fileName, blob.type, defaultTitle));
        } else {
          attachAndSubmitWhenReady(targetTab.id, arrBuf, fileName, blob.type, defaultTitle);
        }
      });
    };
    mediaRecorder.start(1000);
    statusEl.textContent = 'Recording...';
  }

  function attachAndSubmitWhenReady(tabId, arrBuf, fileName, mime, title){
    const inject = ()=>{
      api.scripting.executeScript({
        target: { tabId },
        func: (arrayBuf, fileName, mimeType, titleValue)=>{
          function trySubmit(){
            const uploadForm = document.getElementById('upload-form');
            const fileInput = document.getElementById('audio_file');
            const titleInput = document.getElementById('title');
            if (!uploadForm || !fileInput || !titleInput) return false;
            const dt = new DataTransfer();
            const file = new File([new Blob([arrayBuf], {type: mimeType})], fileName, { type: mimeType });
            dt.items.add(file);
            fileInput.files = dt.files;
            titleInput.value = titleValue;
            if (typeof uploadForm.requestSubmit === 'function') uploadForm.requestSubmit(); else uploadForm.submit();
            return true;
          }
          // Try now, else wait a moment for page render
          if (!trySubmit()) setTimeout(trySubmit, 800);
        },
        args: [arrBuf, fileName, mime, title]
      }, ()=>{
        // no-op
      });
    };

    // Ensure tab loaded
    api.tabs.onUpdated.addListener(function onUpd(id, info){
      if (id === tabId && info.status === 'complete'){
        api.tabs.onUpdated.removeListener(onUpd);
        inject();
      }
    });
    // Also attempt immediate inject (if already loaded)
    inject();
  }

  function stop(){
    stopBtn.disabled = true; startBtn.disabled = false;
    statusEl.textContent = 'Finalizing...';
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
    cleanup();
    statusEl.textContent = 'Done. Uploading...';
  }

  startBtn.addEventListener('click', start);
  stopBtn.addEventListener('click', stop);
})();
