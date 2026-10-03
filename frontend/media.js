// One request at a time per hold; releasing never leaves queued volume repeats.
function createMediaControls({root, send, canSend, reportError, onAction}) {
  let held = null;
  const pointerClicks = new WeakSet();
  const volume = button => ['volume-up','volume-down'].includes(button?.dataset.media);
  function stop() {
    const previous = held;
    held = null;
    if (!previous) return;
    clearTimeout(previous.timer);
    previous.button.classList.remove('is-held');
    if (previous.button.hasPointerCapture?.(previous.pointerId)) {
      previous.button.releasePointerCapture(previous.pointerId);
    }
  }
  async function step(hold) {
    if (held !== hold || !canSend() || !hold.button.isConnected || Date.now()-hold.started>10000) {
      if (held === hold) stop();
      return;
    }
    try {
      await send(hold.button.dataset.media);
      if (held !== hold) return;
      const delay = hold.first ? Math.max(0,400-(Date.now()-hold.started)) : 100;
      hold.first = false;
      hold.timer = setTimeout(()=>step(hold),delay);
    } catch (error) {
      if (held === hold) stop();
      reportError(error);
    }
  }
  root.addEventListener('pointerdown',event=>{
    const button = event.target.closest('button[data-media]');
    if (!volume(button) || button.disabled || event.button!==0 || event.isPrimary===false || !canSend()) return;
    stop();
    pointerClicks.add(button);
    held = {button,pointerId:event.pointerId,started:Date.now(),first:true,timer:null};
    button.classList.add('is-held');
    try {button.setPointerCapture(event.pointerId)} catch {}
    step(held);
  });
  root.addEventListener('click',async event=>{
    const button = event.target.closest('button[data-media]');
    if (!button || button.disabled) return;
    if (event.detail!==0 && pointerClicks.has(button)) {
      pointerClicks.delete(button);
      return; // The pointer press already sent its first step.
    }
    if (!canSend()) return;
    try {await send(button.dataset.media);onAction?.(button.dataset.media)} catch(error) {reportError(error)}
  });
  root.addEventListener('contextmenu',event=>{if(volume(event.target.closest('button[data-media]')))event.preventDefault()});
  window.addEventListener('pointermove',event=>{
    if (!held || event.pointerId!==held.pointerId) return;
    const box=held.button.getBoundingClientRect();
    if(event.clientX<box.left-8||event.clientX>box.right+8||event.clientY<box.top-8||event.clientY>box.bottom+8)stop();
  });
  for(const type of ['pointerup','pointercancel','lostpointercapture']) {
    window.addEventListener(type,event=>{if(held?.pointerId===event.pointerId)stop()});
  }
  window.addEventListener('blur',stop);
  window.addEventListener('pagehide',stop);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState!=='visible')stop()});
  return {stop};
}

function paintMediaPlayback(playback) {
  const status=playback?.status;
  const known=['playing','paused','stopped'].includes(status);
  const label=status==='playing'?'Pause':known?'Play':'Play or pause';
  document.querySelectorAll('[data-media="play-pause"]').forEach(button=>{
    const icon=status==='playing'?'pause':'play';
    if(button.dataset.playbackIcon!==icon){
      button.querySelector('svg')?.remove();
      button.insertAdjacentHTML('afterbegin',glyph(icon));
      button.dataset.playbackIcon=icon;
    }
    button.dataset.playback=known?status:'unknown';
    button.setAttribute('aria-label',label);
    button.title=known?label:'Play or pause · player status unavailable';
    const text=button.querySelector('small');
    if(text)text.textContent=label;
  });
}
