// Desk screens use local media and browser time; they do not imitate sensor readings.
// ambientScenes is supplied before this script from the shared local scene catalog.
function ambientMedia(scene){const extension=scene.type==='video/mp4'?'mp4':'webm';return `/static/assets/${scene.file}.${extension}?v=20261003-collection`}
function ambientPoster(scene){return `/static/assets/${scene.file}.jpg?v=20261003-collection`}
const screenPreferences={format:'24',scene:Object.keys(ambientScenes)[0]||null,motion:!matchMedia('(prefers-reduced-motion: reduce)').matches};
try{Object.assign(screenPreferences,JSON.parse(localStorage.getItem('g16-screen-preferences')||'{}'))}catch{}
if(!['24','12'].includes(screenPreferences.format))screenPreferences.format='24';
if(!Object.hasOwn(ambientScenes,screenPreferences.scene))screenPreferences.scene=Object.keys(ambientScenes)[0]||null;
if(typeof screenPreferences.motion!=='boolean')screenPreferences.motion=true;
let presentation=false;
function saveScreenPreferences(){try{localStorage.setItem('g16-screen-preferences',JSON.stringify(screenPreferences))}catch{}}
function screenActions(){return `<div class="screen-actions"><button data-screen-focus aria-label="Immersive view">${glyph('fullscreen')}<span>Immersive view</span></button><button data-screen-awake>${glyph('clock')}<span>Keep awake</span></button></div>`}
function flipTile(unit){return `<div class="flip-tile" data-flip-unit="${unit}"><span class="flip-value" data-clock-${unit}>00</span>${['top','bottom','leaf-top','leaf-bottom'].map(face=>`<span class="flip-face flip-${face}" aria-hidden="true"><span class="flip-numeral">00</span></span>`).join('')}<i class="flip-hinge" aria-hidden="true"></i></div>`}
function clockScreen(){if(focusView)return focusScreen();if(widgetPreferences.clocks&&widgetPreferences.clock!=='flip')return nativeClockScreen();return `<article class="desk-screen clock-screen"><div class="screen-kicker"><span>JARVIS / FLIP CLOCK</span><span data-clock-zone></span></div><div class="clock-composition"><div class="digital-clock"><div class="clock-greeting" data-clock-greeting></div><div class="clock-digits flip-clock" role="timer" aria-live="off" aria-label="Current local time">${flipTile('hours')}<span class="clock-colon" aria-hidden="true">:</span>${flipTile('minutes')}</div><div class="clock-meta"><span data-clock-date></span><span class="clock-seconds"><b data-clock-seconds>00</b> <span data-clock-period>SEC</span></span></div></div></div><div class="screen-bottom"><div class="segmented"><button data-clock-format="24" class="${screenPreferences.format==='24'?'active':''}">24 H</button><button data-clock-format="12" class="${screenPreferences.format==='12'?'active':''}">12 H</button><button data-clock-mode="focus">Focus timer</button><button data-go="rest">Rest & alarms</button></div>${clockFacePicker()}${screenActions()}</div><button class="exit-immersive" data-screen-exit aria-label="Exit immersive view">${glyph('arrow')}<span>Back to display</span></button></article>`}

const flipTimers=new WeakMap();
const clockMotion=matchMedia('(prefers-reduced-motion: reduce)');
function setFlipValue(tile,value,animate=true){
  if(tile.dataset.value===value&&animate)return;
  clearTimeout(flipTimers.get(tile));
  const previous=tile.dataset.value;
  tile.dataset.value=value;
  tile.querySelector('.flip-value').textContent=value;
  tile.classList.remove('flipping');
  const face=name=>tile.querySelector(`.flip-${name} .flip-numeral`);
  const finish=()=>{tile.classList.remove('flipping');face('bottom').textContent=value;flipTimers.delete(tile)};
  face('top').textContent=value;
  face('bottom').textContent=previous||value;
  face('leaf-top').textContent=previous||value;
  face('leaf-bottom').textContent=value;
  if(previous&&animate&&!clockMotion.matches&&document.visibilityState==='visible'&&!document.querySelector('#pair-dialog').open){
    void tile.offsetWidth;
    tile.classList.add('flipping');
    flipTimers.set(tile,setTimeout(finish,600));
  }else finish();
}
function ambientScreen(){
  const scene=ambientScenes[screenPreferences.scene];
  if(!scene)return '<article class="desk-screen ambient-screen"><div class="screen-kicker">JARVIS / AMBIENT COLLECTION</div><p>Local ambient scenes are unavailable.</p></article>';
  return `<article class="desk-screen ambient-screen" data-scene="${screenPreferences.scene}" data-motion="${screenPreferences.motion}"><video id="ambient-video" data-scene="${screenPreferences.scene}" muted loop playsinline preload="metadata" src="${ambientMedia(scene)}" poster="${ambientPoster(scene)}" aria-label="${escapeHtml(scene.name)} ambient animation"></video><div class="ambient-vignette"></div><div class="screen-kicker"><span>JARVIS / AMBIENT COLLECTION</span><span>VOL. 01</span></div><div class="ambient-caption"><span class="ambient-number">${scene.number}</span><h2 id="scene-name">${escapeHtml(scene.name)}</h2><p id="scene-description">${escapeHtml(scene.description)}</p><p id="scene-credit" class="scene-credit" ${scene.credit?'':'hidden'}>${escapeHtml(scene.credit)}</p></div><div class="ambient-live-clock"><span data-ambient-time></span><small data-clock-date></small></div><div class="screen-bottom"><div class="scene-controls" aria-label="Ambient scenes">${Object.entries(ambientScenes).map(([id,item])=>`<button data-scene-select="${id}" class="${screenPreferences.scene===id?'active':''}">${escapeHtml(item.name)}</button>`).join('')}<button data-motion-toggle aria-label="Pause animation">${glyph(screenPreferences.motion?'pause':'play')}</button></div>${screenActions()}</div><button class="exit-immersive" data-screen-exit>${glyph('arrow')}<span>Back to display</span></button></article>`;
}
function updateClock(now=new Date(),animate=true){
  paintNativeClock(now);
  const hour=now.getHours(),minute=now.getMinutes(),second=now.getSeconds();
  const displayHour=screenPreferences.format==='12'?hour%12||12:hour;
  const values={'clock-hours':String(displayHour).padStart(2,'0'),'clock-minutes':String(minute).padStart(2,'0'),'clock-seconds':String(second).padStart(2,'0'),'clock-period':screenPreferences.format==='12'?(hour<12?'AM':'PM'):'SEC','clock-date':now.toLocaleDateString([],{weekday:'long',month:'long',day:'numeric'}),'clock-zone':Intl.DateTimeFormat().resolvedOptions().timeZone.replaceAll('_',' '),'clock-greeting':hour<12?'Good morning, sir.':hour<18?'Good afternoon, sir.':'Good evening, sir.','ambient-time':now.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:screenPreferences.format==='12'})};
  for(const [key,value] of Object.entries(values))document.querySelectorAll(`[data-${key}]`).forEach(el=>{
    const tile=el.closest('.flip-tile');
    if(tile)setFlipValue(tile,value,animate);else el.textContent=value;
  });
  const timer=document.querySelector('.flip-clock');
  if(timer)timer.setAttribute('aria-label',`${values['clock-hours']}:${values['clock-minutes']}${screenPreferences.format==='12'?' '+values['clock-period']:''}`);
}
function updateAmbient(){
  const screen=document.querySelector('.ambient-screen');if(!screen)return;
  screen.dataset.scene=screenPreferences.scene;screen.dataset.motion=String(screenPreferences.motion);
  const scene=ambientScenes[screenPreferences.scene];
  if(!scene)return;
  screen.querySelector('.ambient-number').textContent=scene.number;document.querySelector('#scene-name').textContent=scene.name;document.querySelector('#scene-description').textContent=scene.description;
  const credit=screen.querySelector('#scene-credit');credit.textContent=scene.credit;credit.hidden=!scene.credit;
  screen.querySelectorAll('[data-scene-select]').forEach(el=>el.classList.toggle('active',el.dataset.sceneSelect===screenPreferences.scene));
  const toggle=screen.querySelector('[data-motion-toggle]');toggle.innerHTML=glyph(screenPreferences.motion?'pause':'play');toggle.setAttribute('aria-label',screenPreferences.motion?'Pause animation':'Play animation');
  const video=document.querySelector('#ambient-video');
  if(video.dataset.scene!==screenPreferences.scene){video.pause();video.dataset.scene=screenPreferences.scene;video.poster=ambientPoster(scene);video.src=ambientMedia(scene);video.setAttribute('aria-label',`${scene.name} ambient animation`);video.load()}
  const selected=screenPreferences.scene;
  if(screenPreferences.motion&&document.visibilityState==='visible'&&!document.querySelector('#pair-dialog').open)video.play().catch(error=>{if(!video.isConnected||error.name==='AbortError'||screenPreferences.scene!==selected||!screenPreferences.motion)return;screenPreferences.motion=false;screen.dataset.motion='false';toggle.innerHTML=glyph('play');toggle.setAttribute('aria-label','Play animation')});else video.pause();
}
function setPresentation(enabled){presentation=enabled;document.body.classList.toggle('presentation',enabled)}
function mountScreens(){if(!['clock','ambient','media','rest','widgets'].includes(state.page))setPresentation(false);updateClock();updateAmbient();if(state.page==='games')paintGames()}
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&presentation)setPresentation(false)});
document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&presentation)setPresentation(false)});
document.addEventListener('visibilitychange',updateAmbient);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')updateClock(new Date(),false)});
clockMotion.addEventListener('change',()=>updateClock(new Date(),false));
setInterval(updateClock,1000);
