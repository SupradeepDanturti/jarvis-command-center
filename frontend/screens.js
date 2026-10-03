// Desk screens are local artwork and browser time; they do not imitate sensor readings.
const screenPreferences={format:'24',scene:'horizon',motion:!matchMedia('(prefers-reduced-motion: reduce)').matches};
try{Object.assign(screenPreferences,JSON.parse(localStorage.getItem('g16-screen-preferences')||'{}'))}catch{}
if(!['24','12'].includes(screenPreferences.format))screenPreferences.format='24';
if(!['horizon','grid','aurora'].includes(screenPreferences.scene))screenPreferences.scene='horizon';
if(typeof screenPreferences.motion!=='boolean')screenPreferences.motion=true;
let presentation=false;
function saveScreenPreferences(){try{localStorage.setItem('g16-screen-preferences',JSON.stringify(screenPreferences))}catch{}}
function screenActions(){return `<div class="screen-actions"><button data-screen-focus>${glyph('fullscreen')}<span>Immersive view</span></button><button data-screen-awake>${glyph('clock')}<span>Keep awake</span></button></div>`}
function clockScreen(){return `<article class="desk-screen clock-screen"><div class="screen-kicker"><span>G16 / TIME STATION</span><span data-clock-zone></span></div><div class="clock-composition"><div class="clock-dial" aria-hidden="true"><div class="dial-orbit"></div><span class="dial-top">12</span><span class="dial-right">3</span><span class="dial-bottom">6</span><span class="dial-left">9</span><i class="clock-hand hour-hand"></i><i class="clock-hand minute-hand"></i><i class="clock-hand second-hand"></i><i class="dial-center"></i><img src="/static/assets/g16-mark.svg" alt="" class="dial-mark"></div><div class="digital-clock"><div class="clock-greeting" data-clock-greeting></div><div class="clock-digits" role="timer" aria-label="Current local time"><span data-clock-hours>00</span><span class="clock-colon">:</span><span data-clock-minutes>00</span></div><div class="clock-meta"><span data-clock-date></span><span class="clock-seconds"><b data-clock-seconds>00</b> <span data-clock-period>SEC</span></span></div></div></div><div class="screen-bottom"><div class="segmented"><button data-clock-format="24" class="${screenPreferences.format==='24'?'active':''}">24 H</button><button data-clock-format="12" class="${screenPreferences.format==='12'?'active':''}">12 H</button></div>${screenActions()}</div><button class="exit-immersive" data-screen-exit aria-label="Exit immersive view">${glyph('arrow')}<span>Back to display</span></button></article>`}
function ambientScreen(){return `<article class="desk-screen ambient-screen" data-scene="${screenPreferences.scene}" data-motion="${screenPreferences.motion}"><video id="ambient-video" muted loop playsinline preload="metadata" poster="/static/assets/event-horizon.jpg" aria-label="Original event horizon ambient animation"><source src="/static/assets/event-horizon.webm" type="video/webm"></video><div class="ambient-aurora" aria-hidden="true"><i></i><i></i><i></i></div><div class="ambient-grid" aria-hidden="true"></div><div class="ambient-vignette"></div><div class="screen-kicker"><span>G16 / AMBIENT COLLECTION</span><span>VOL. 01</span></div><div class="ambient-caption"><span class="ambient-number">01 /</span><h2 id="scene-name">Event horizon</h2><p id="scene-description">A little space for your desk.</p></div><div class="ambient-live-clock"><span data-ambient-time></span><small data-clock-date></small></div><div class="screen-bottom"><div class="scene-controls" aria-label="Ambient scenes">${[['horizon','Event horizon'],['grid','Neon drift'],['aurora','Aurora']].map(([id,name])=>`<button data-scene-select="${id}" class="${screenPreferences.scene===id?'active':''}">${name}</button>`).join('')}<button data-motion-toggle aria-label="Pause animation">${glyph(screenPreferences.motion?'pause':'play')}</button></div>${screenActions()}</div><button class="exit-immersive" data-screen-exit>${glyph('arrow')}<span>Back to display</span></button></article>`}
function updateClock(){
  const now=new Date();
  const hour=now.getHours(),minute=now.getMinutes(),second=now.getSeconds();
  const displayHour=screenPreferences.format==='12'?hour%12||12:hour;
  const values={'clock-hours':String(displayHour).padStart(2,'0'),'clock-minutes':String(minute).padStart(2,'0'),'clock-seconds':String(second).padStart(2,'0'),'clock-period':screenPreferences.format==='12'?(hour<12?'AM':'PM'):'SEC','clock-date':now.toLocaleDateString([],{weekday:'long',month:'long',day:'numeric'}),'clock-zone':Intl.DateTimeFormat().resolvedOptions().timeZone.replaceAll('_',' '),'clock-greeting':hour<12?'Make room for a good morning.':hour<18?'Your afternoon, in focus.':'Slow down. Stay connected.','ambient-time':now.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:screenPreferences.format==='12'})};
  for(const [key,value] of Object.entries(values))document.querySelectorAll(`[data-${key}]`).forEach(el=>el.textContent=value);
  const dial=document.querySelector('.clock-dial');
  if(dial){dial.style.setProperty('--hour',`${(hour%12)*30+minute/2}deg`);dial.style.setProperty('--minute',`${minute*6+second/10}deg`);dial.style.setProperty('--second',`${second*6}deg`)}
}
function updateAmbient(){
  const screen=document.querySelector('.ambient-screen');if(!screen)return;
  screen.dataset.scene=screenPreferences.scene;screen.dataset.motion=String(screenPreferences.motion);
  const scenes={horizon:['01 /','Event horizon','A little space for your desk.'],grid:['02 /','Neon drift','Follow the light. Find your rhythm.'],aurora:['03 /','Aurora','Color in motion. A quieter kind of energy.']};
  const scene=scenes[screenPreferences.scene]||scenes.horizon;
  screen.querySelector('.ambient-number').textContent=scene[0];document.querySelector('#scene-name').textContent=scene[1];document.querySelector('#scene-description').textContent=scene[2];
  screen.querySelectorAll('[data-scene-select]').forEach(el=>el.classList.toggle('active',el.dataset.sceneSelect===screenPreferences.scene));
  const toggle=screen.querySelector('[data-motion-toggle]');toggle.innerHTML=glyph(screenPreferences.motion?'pause':'play');toggle.setAttribute('aria-label',screenPreferences.motion?'Pause animation':'Play animation');
  const video=document.querySelector('#ambient-video');
  if(screenPreferences.motion&&screenPreferences.scene==='horizon'&&document.visibilityState==='visible'&&!document.querySelector('#pair-dialog').open)video.play().catch(error=>{if(!video.isConnected||error.name==='AbortError'||screenPreferences.scene!=='horizon')return;screenPreferences.motion=false;screen.dataset.motion='false';toggle.innerHTML=glyph('play');toggle.setAttribute('aria-label','Play animation')});else video.pause();
}
function setPresentation(enabled){presentation=enabled;document.body.classList.toggle('presentation',enabled)}
function mountScreens(){if(!['clock','ambient'].includes(state.page))setPresentation(false);updateClock();updateAmbient();if(state.page==='games')paintGames()}
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&presentation)setPresentation(false)});
document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&presentation)setPresentation(false)});
document.addEventListener('visibilitychange',updateAmbient);
setInterval(updateClock,1000);
