// The HUD visualizes reported worker phases, not microphone levels or simulated checks.
let jarvisStatusFreshAt=0,jarvisVisualEpoch=0;
const jarvisPhaseLabels={off:'Standing by.',starting:'Initializing.',listening:'Wake word armed.',recording:'I’m listening.',transcribing:'Understanding you.',thinking:'Processing request.',speaking:'Jarvis is speaking.',followup:'Your turn.',locked:'Laptop locked.',preview:'Voice preview.',alert:'System alert.',error:'Needs attention.'};
function jarvisCore(){return `<div class="jarvis-core" aria-hidden="true"><div class="jarvis-ring jarvis-ring-outer"></div><div class="jarvis-ring jarvis-ring-inner"></div><img class="jarvis-mask" src="/static/assets/iron-man-helmet.png" alt="" width="120" height="140"><div class="jarvis-scan"></div></div>`}
function jarvisHome(){return `<aside id="jarvis-home" class="jarvis-home" hidden aria-label="Jarvis activity"><div class="jarvis-idle"><img src="/static/assets/iron-man-helmet.png" alt="" width="24" height="28"><span>JARVIS <b id="jarvis-idle-label">Wake word armed</b></span></div><div class="jarvis-home-active"><div class="jarvis-hud-rail"><span>J.A.R.V.I.S.</span><span>G16 / VOICE LINK</span></div><div class="jarvis-home-center">${jarvisCore()}<div class="jarvis-home-copy"><span class="jarvis-overline">VOICE ACTIVITY</span><h3 id="jarvis-home-phase" role="status" aria-live="polite"></h3><div class="jarvis-wave" aria-hidden="true">${Array.from({length:13},()=>'<i></i>').join('')}</div><p id="jarvis-home-caption"></p></div></div><div class="jarvis-hud-rail jarvis-readings"><span>LIVE READINGS</span><span>CPU <b data-jarvis-value="cpu"></b></span><span>RAM <b data-jarvis-value="memory"></b></span><span>GPU <b data-jarvis-value="gpu"></b></span></div></div></aside>`}
function resetJarvisVisuals(){jarvisVisualEpoch++;jarvisStatusFreshAt=0;voiceState=null;voiceHistoryRows=[];voiceHistoryMark=null;document.querySelector('#jarvis-home')?.setAttribute('hidden','')}
function paintJarvisHome(){
  const hud=document.querySelector('#jarvis-home');if(!hud)return;
  const status=voiceState,fresh=Date.now()-jarvisStatusFreshAt<5500;
  const visible=state.paired&&!state.stale&&document.visibilityState==='visible'&&fresh&&status?.busy;
  hud.hidden=!visible;if(!visible)return;
  const phase=status.phase;
  const active=['starting','recording','transcribing','thinking','speaking','followup','preview','alert'].includes(phase);
  hud.dataset.phase=phase;hud.dataset.active=String(active);
  document.querySelector('#jarvis-idle-label').textContent=phase==='locked'?'Paused · laptop locked':phase==='error'?'Needs attention':'Wake word armed';
  document.querySelector('#jarvis-home-phase').textContent=jarvisPhaseLabels[phase]||'Working on your request.';
  document.querySelector('#jarvis-home-caption').textContent=(['speaking','followup','alert'].includes(phase)&&status.lastReply?status.lastReply:status.message||'').slice(0,190);
  const data=state.data;
  for(const [name,value,suffix] of [['cpu',data?.cpu?.usage,'%'],['memory',data?.memory?.percent,'%'],['gpu',data?.gpu?.temperature,'°']]){
    hud.querySelector(`[data-jarvis-value="${name}"]`).textContent=value==null?'—':Math.round(value)+suffix;
  }
}
document.addEventListener('visibilitychange',()=>{document.body.classList.toggle('jarvis-hidden',document.visibilityState!=='visible');if(document.visibilityState!=='visible')jarvisStatusFreshAt=0;paintJarvisHome()});
