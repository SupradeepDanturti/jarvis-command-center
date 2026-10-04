// Screen wake locks belong to this visible, approved browser, not the PC server.
let keepAwake=true;
try{keepAwake=localStorage.getItem('g16-keep-awake')!=='false'}catch{}
let screenWakeLock=null,wakeRequest=null,wakeRetryTimer=null,wakeGeneration=0;
let wakeStatus='waiting',wakeRetryDelay=2000,wakeLastAttempt=0,wakeWarningShown=false,wakePageActive=true;
function wantsScreenAwake(){return keepAwake&&wakePageActive&&state.paired&&document.visibilityState==='visible'&&!document.querySelector('#pair-dialog').open}
function supportsScreenAwake(){return isSecureContext&&typeof navigator.wakeLock?.request==='function'}
function paintScreenAwake(){
  document.body.dataset.awake=wakeStatus;
  const labels={waiting:'Waiting for approval',off:'Off',paused:'Paused while away',requesting:'Requesting…',active:'Active · screen stays on',released:'Released · retrying',blocked:'Blocked by browser',unsupported:'Unavailable in this browser'};
  const status=document.querySelector('#wake-status');if(status)status.textContent=labels[wakeStatus];
  const toggle=document.querySelector('#wake-lock');
  if(toggle){toggle.textContent=keepAwake?'Turn keep-awake off':'Keep screen awake';toggle.setAttribute('aria-pressed',String(keepAwake))}
  const retry=document.querySelector('#wake-retry');if(retry)retry.hidden=!['blocked','released'].includes(wakeStatus);
  const note=document.querySelector('#wake-help');
  if(note)note.textContent=wakeStatus==='blocked'||wakeStatus==='released'?'The browser released or declined keep-awake. Turn off tablet Battery saver, then tap Retry.':wakeStatus==='unsupported'?'Open the trusted HTTPS dashboard in an up-to-date browser with screen wake-lock support.':'Keep-awake starts automatically on approved pages and resumes when you return. Turn it off to allow normal screen sleep.';
  document.querySelectorAll('[data-screen-awake]').forEach(button=>{
    button.querySelector('span').textContent=wakeStatus==='active'?'Screen awake':['blocked','released'].includes(wakeStatus)?'Retry keep awake':'Keep awake';
    button.setAttribute('aria-pressed',String(wakeStatus==='active'));
    button.setAttribute('aria-label',wakeStatus==='active'?'Allow screen to sleep':keepAwake?'Retry keeping screen awake':'Keep screen awake');
  });
}
function wakeSettings(){return `<div class="detail-row"><span>Screen keep-awake</span><strong id="wake-status" role="status" aria-live="polite"></strong></div><p id="wake-help" class="section-note"></p>`}
function clearWakeRetry(){clearTimeout(wakeRetryTimer);wakeRetryTimer=null}
function retryScreenAwakeLater(){
  if(!wantsScreenAwake()||!supportsScreenAwake()||wakeRetryTimer)return;
  wakeRetryTimer=setTimeout(()=>{wakeRetryTimer=null;syncScreenAwake()},wakeRetryDelay);
  wakeRetryDelay=Math.min(wakeRetryDelay*2,30000);
}
async function releaseScreenAwake(){
  const lock=screenWakeLock;screenWakeLock=null;
  if(lock&&!lock.released)await lock.release().catch(()=>{});
}
function syncScreenAwake(){
  if(!wantsScreenAwake()){
    wakeGeneration++;clearWakeRetry();
    wakeStatus=!keepAwake?'off':!state.paired?'waiting':'paused';paintScreenAwake();
    return releaseScreenAwake().then(()=>false);
  }
  if(!supportsScreenAwake()){wakeStatus='unsupported';paintScreenAwake();return Promise.resolve(false)}
  if(screenWakeLock&&!screenWakeLock.released){wakeStatus='active';paintScreenAwake();return Promise.resolve(true)}
  if(wakeRequest)return wakeRequest;
  clearWakeRetry();wakeLastAttempt=Date.now();wakeStatus='requesting';paintScreenAwake();
  const generation=wakeGeneration;
  const pending=Promise.resolve().then(async()=>{
    try{
      const lock=await navigator.wakeLock.request('screen');
      if(generation!==wakeGeneration||!wantsScreenAwake()){
        if(!lock.released)await lock.release().catch(()=>{});
        return false;
      }
      if(lock.released){wakeStatus='released';paintScreenAwake();retryScreenAwakeLater();return false}
      screenWakeLock=lock;wakeRetryDelay=2000;wakeStatus='active';paintScreenAwake();
      lock.addEventListener('release',()=>{
        if(screenWakeLock!==lock)return;
        screenWakeLock=null;wakeStatus=wantsScreenAwake()?'released':!keepAwake?'off':!state.paired?'waiting':'paused';
        paintScreenAwake();retryScreenAwakeLater();
      },{once:true});
      return true;
    }catch{
      if(generation!==wakeGeneration||!wantsScreenAwake())return false;
      wakeStatus='blocked';paintScreenAwake();retryScreenAwakeLater();
      if(!wakeWarningShown){wakeWarningShown=true;toast('Keep-awake was declined. Check tablet Battery saver, then Retry in Tablet settings.')}
      return false;
    }finally{
      if(wakeRequest===pending)wakeRequest=null;
      // A stale request must settle before acquiring a replacement lock.
      if(generation!==wakeGeneration&&wantsScreenAwake())syncScreenAwake();
    }
  });
  wakeRequest=pending;return pending;
}
function setKeepAwake(enabled){
  keepAwake=enabled;wakeRetryDelay=2000;clearWakeRetry();
  try{localStorage.setItem('g16-keep-awake',String(enabled))}catch{}
  return syncScreenAwake();
}
function retryScreenAwake(){clearWakeRetry();wakeRetryDelay=2000;return syncScreenAwake()}
function suspendScreenAwake(){wakePageActive=false;wakeGeneration++;clearWakeRetry();wakeStatus=keepAwake?'paused':'off';paintScreenAwake();return releaseScreenAwake()}
document.addEventListener('visibilitychange',syncScreenAwake);
document.addEventListener('fullscreenchange',syncScreenAwake);
window.addEventListener('focus',syncScreenAwake);
window.addEventListener('pageshow',()=>{wakePageActive=true;syncScreenAwake()});
window.addEventListener('pagehide',suspendScreenAwake);
document.addEventListener('pointerdown',event=>{
  if(event.target.closest('#wake-lock,#wake-retry,[data-screen-awake]'))return;
  if(wantsScreenAwake()&&!screenWakeLock&&Date.now()-wakeLastAttempt>=2000)retryScreenAwake();
},{passive:true});
