// One shared local backdrop: page changes never stack video players.
const backgroundPreferences={scene:'auto',motion:true};
try{Object.assign(backgroundPreferences,JSON.parse(localStorage.getItem('g16-background-preferences')||'{}'))}catch{}
if(backgroundPreferences.scene!=='auto'&&!Object.hasOwn(ambientScenes,backgroundPreferences.scene))backgroundPreferences.scene='auto';
if(typeof backgroundPreferences.motion!=='boolean')backgroundPreferences.motion=true;
const backgroundMotion=matchMedia('(prefers-reduced-motion: reduce)');
const pageBackgrounds={home:'horizon',gaming:'grid',games:'blackhole',apps:'aurora',hardware:'horizon',graphs:'grid',system:'aurora',devices:'aurora',clock:'horizon'};
let backgroundGeneration=0;
function saveBackgroundPreferences(){try{localStorage.setItem('g16-background-preferences',JSON.stringify(backgroundPreferences))}catch{}}
function backgroundSettings(){
  return `<div class="detail-row background-setting"><label for="background-scene">Background scene</label><select id="background-scene">${[['auto','Match each screen'],...Object.entries(ambientScenes).map(([id,scene])=>[id,scene.name])].map(([id,name])=>`<option value="${id}" ${backgroundPreferences.scene===id?'selected':''}>${name}</option>`).join('')}</select></div><div class="page-actions"><button id="background-motion" aria-pressed="${backgroundPreferences.motion}" ${backgroundMotion.matches?'disabled':''}>${backgroundMotion.matches?'Motion reduced':backgroundPreferences.motion?'Pause backgrounds':'Resume backgrounds'}</button></div><p class="section-note">Local artwork behind your screens. Motion pauses while hidden and follows your device’s reduced-motion setting. Ambient has its own scene controls.</p>`;
}
function updateSurfaceBackground(){
  const layer=document.querySelector('.surface-backdrop'),video=document.querySelector('#surface-background');
  const dedicated=state.page==='ambient';layer.hidden=dedicated;
  if(dedicated){video.pause();return}
  const id=backgroundPreferences.scene==='auto'?(pageBackgrounds[state.page]||'aurora'):backgroundPreferences.scene;
  const scene=ambientScenes[id];
  if(video.dataset.scene!==id){
    backgroundGeneration++;
    video.pause();video.dataset.scene=id;video.poster=ambientPoster(scene);video.src=ambientMedia(scene);video.load();
  }
  const playing=backgroundPreferences.motion&&!backgroundMotion.matches&&document.visibilityState==='visible'&&state.paired&&!document.querySelector('#pair-dialog').open;
  layer.dataset.motion=String(playing);
  const generation=backgroundGeneration;
  if(playing)video.play().catch(error=>{
    if(generation!==backgroundGeneration||error.name==='AbortError'||document.visibilityState!=='visible')return;
    layer.dataset.motion='false'; // Retain the still poster if playback is unavailable.
  });else video.pause();
  const button=document.querySelector('#background-motion');
  if(button){button.disabled=backgroundMotion.matches;button.textContent=backgroundMotion.matches?'Motion reduced':backgroundPreferences.motion?'Pause backgrounds':'Resume backgrounds';button.setAttribute('aria-pressed',String(backgroundPreferences.motion))}
}
document.addEventListener('visibilitychange',updateSurfaceBackground);
backgroundMotion.addEventListener('change',updateSurfaceBackground);
document.addEventListener('change',event=>{
  if(event.target.id!=='background-scene')return;
  const selected=event.target.value;
  if(selected!=='auto'&&!Object.hasOwn(ambientScenes,selected))return;
  backgroundPreferences.scene=selected;saveBackgroundPreferences();updateSurfaceBackground();
});
document.addEventListener('click',event=>{
  if(!event.target.closest('#background-motion'))return;
  backgroundPreferences.motion=!backgroundPreferences.motion;saveBackgroundPreferences();updateSurfaceBackground();
});
