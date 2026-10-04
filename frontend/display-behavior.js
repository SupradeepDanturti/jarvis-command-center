// One deterministic policy for automatic navigation. Manual input always wins.
const displayPages=['home','clock','ambient','gaming','media','widgets'];
const displayDefaults={night:false,start:'22:00',end:'07:00',level:35,rotation:false,dwell:120,pages:['home','clock','ambient'],media:false,games:false};
function normalizeDisplayPreferences(value){
  const data={...displayDefaults,pages:[...displayDefaults.pages]};
  if(!value||typeof value!=='object')return data;
  for(const key of ['night','rotation','media','games'])if(typeof value[key]==='boolean')data[key]=value[key];
  for(const key of ['start','end'])if(typeof value[key]==='string'&&/^([01]\d|2[0-3]):[0-5]\d$/.test(value[key]))data[key]=value[key];
  if(data.start===data.end)data.night=false;
  if(Number.isInteger(value.level)&&value.level>=15&&value.level<=80)data.level=value.level;
  if(Number.isInteger(value.dwell)&&value.dwell>=30&&value.dwell<=600)data.dwell=value.dwell;
  if(Array.isArray(value.pages)){const allowed=[...new Set(value.pages.filter(page=>displayPages.includes(page)))];if(allowed.length>=2)data.pages=allowed}
  return data;
}
function nightActive(prefs,date){const at=text=>Number(text.slice(0,2))*60+Number(text.slice(3));const minutes=date.getHours()*60+date.getMinutes(),start=at(prefs.start),end=at(prefs.end);return prefs.night&&start!==end&&(start<end?minutes>=start&&minutes<end:minutes>=start||minutes<end)}
function createDisplayPolicy(now=()=>performance.now()){
  let prefs=normalizeDisplayPreferences(null),manualPage='home',hold=0,next=now()+120000,pinned=false,blocked=true;
  let observed='',candidateAt=now(),consumed='',automatic='';
  return {
    get preferences(){return prefs},get pinned(){return pinned},
    configure(value){prefs=normalizeDisplayPreferences(value);next=now()+prefs.dwell*1000;automatic='';consumed='';candidateAt=now()},
    togglePin(){pinned=!pinned;next=now()+prefs.dwell*1000;return pinned},
    manual(page){if(displayPages.includes(page))manualPage=page;hold=now()+120000;next=hold+prefs.dwell*1000;consumed=observed;automatic=''},
    tick(context){
      const time=now();
      const signature=prefs.games&&context.game?`game:${context.game.id}`:prefs.media&&!context.game&&context.playing?`media:${context.sessionId}`:'';
      if(signature!==observed){observed=signature;candidateAt=time;consumed=''}
      const stop=!context.ready||context.interacting||context.menu||context.presentation||context.focus||pinned||!displayPages.includes(context.page)||time<hold;
      if(stop){blocked=true;next=Math.max(next,time+prefs.dwell*1000);return null}
      if(blocked){blocked=false;next=time+prefs.dwell*1000;candidateAt=time;return null}
      if(signature&&time-candidateAt>=5000&&signature!==consumed){consumed=signature;automatic=signature;next=time+prefs.dwell*1000;return signature.startsWith('game:')?'gaming':'media'}
      if(automatic&&signature===automatic)return null;
      if(automatic&&!signature){if(time-candidateAt<10000)return null;automatic='';next=time+prefs.dwell*1000;return prefs.rotation?(prefs.pages.includes(manualPage)?manualPage:prefs.pages[0]):manualPage}
      if(prefs.rotation&&time>=next){next=time+prefs.dwell*1000;const rotation=prefs.pages.filter(page=>page!=='widgets'||context.widgetsEnabled!==false);if(rotation.length<2)return null;const current=rotation.indexOf(context.page);return rotation[(current+1)%rotation.length]}
      return null;
    }
  };
}
const displayBehavior=createDisplayPolicy();
try{displayBehavior.configure(JSON.parse(localStorage.getItem('g16-display-behavior')||'{}'))}catch{}
let brightenUntil=0,deskPointer=false,activityState=null,activityReceipt=0;
function displayBehaviorSettings(){const prefs=displayBehavior.preferences;return `<section class="desk-settings"><h3>Display behavior</h3><form id="display-behavior-settings"><label class="setting-check"><input type="checkbox" name="night" ${prefs.night?'checked':''}>Scheduled night dimming</label><div class="settings-fields"><label>From<input type="time" name="start" value="${prefs.start}" required></label><label>Until<input type="time" name="end" value="${prefs.end}" required></label><label>Scene brightness · %<input type="number" name="level" min="15" max="80" value="${prefs.level}" required></label></div><p class="section-note">Uses this device's local time. Dims the dashboard artwork; tablet hardware brightness stays under Android's control.</p><button type="button" data-brighten>Brighten for 15 minutes</button><label class="setting-check"><input type="checkbox" name="rotation" ${prefs.rotation?'checked':''}>Slow screen rotation</label><label>Seconds per screen<input type="number" name="dwell" min="30" max="600" value="${prefs.dwell}" required></label><div class="rotation-options">${displayPages.map(page=>`<label class="setting-check"><input type="checkbox" name="pages" value="${page}" ${prefs.pages.includes(page)?'checked':''}>${{home:'Home',clock:'Clock',ambient:'Ambient',gaming:'Live',media:'Now playing',widgets:'Widgets'}[page]}</label>`).join('')}</div><label class="setting-check"><input type="checkbox" name="media" ${prefs.media?'checked':''}>Switch for playing media</label><label class="setting-check"><input type="checkbox" name="games" ${prefs.games?'checked':''}>Switch for a recognized foreground game</label><p class="section-note">Touch holds your view for two minutes. Settings, immersive views and an active Focus view stay put. Foreground games take priority over music.</p><button type="submit">Save display behavior</button></form><p id="display-behavior-status" class="section-note"></p></section>`}
function tickDisplayBehavior(date=new Date()){
  const prefs=displayBehavior.preferences,dim=state.paired&&!document.querySelector('#pair-dialog').open&&nightActive(prefs,date)&&performance.now()>=brightenUntil;
  document.body.classList.toggle('night-dim',dim);document.documentElement.style.setProperty('--night-level',String(prefs.level/100));
  const fresh=deskControlsReady();
  const target=displayBehavior.tick({widgetsEnabled:widgetsEnabled(),page:state.page,ready:fresh&&!state.stale,interacting:deskPointer||!!mediaDrag||!!mediaPending||!!focusPending,
    menu:!!restState?.rest||!document.querySelector('#more-menu').hidden||!!document.querySelector('dialog[open]'),presentation,
    focus:focusView&&state.page==='clock'&&['running','paused'].includes(focusState?.status),
    game:fresh&&performance.now()-activityReceipt<5000?activityState?.game:null,
    playing:fresh&&performance.now()-mediaReceipt<5000&&state.playback?.status==='playing',sessionId:state.playback?.sessionId});
  if(target&&target!==state.page){goPage(target,'automatic');toast(target==='gaming'?'Your game readings, sir.':target==='media'?'Your music, sir.':'As requested, sir.')}
  const status=document.querySelector('#display-behavior-status');if(status)status.textContent=displayBehavior.pinned?'Pinned until you choose Resume automatic display.':dim?'Night dimming active.':prefs.rotation||prefs.media||prefs.games?'Automatic display enabled. Manual controls take priority.':'Automatic navigation off.';
  document.querySelectorAll('[data-desk-pin]').forEach(button=>button.textContent=displayBehavior.pinned?'Resume automatic display':'Stay on this screen');
}
function installDisplayBehavior(root){
  document.addEventListener('pointerdown',()=>{deskPointer=true;displayBehavior.manual(state.page)},{passive:true});
  for(const event of ['pointerup','pointercancel'])window.addEventListener(event,()=>{deskPointer=false;displayBehavior.manual(state.page)});
  for(const event of ['keydown','wheel','touchmove'])document.addEventListener(event,()=>displayBehavior.manual(state.page),{passive:true});
  window.addEventListener('blur',()=>{deskPointer=false;displayBehavior.manual(state.page)});
  document.addEventListener('visibilitychange',()=>{deskPointer=false;displayBehavior.manual(state.page);tickDisplayBehavior()});
  document.addEventListener('click',event=>{const button=event.target.closest('[data-desk-pin],[data-brighten]');if(!button)return;if(button.hasAttribute('data-brighten'))brightenUntil=performance.now()+900000;else{displayBehavior.togglePin();closeMore()}tickDisplayBehavior()});
  root.addEventListener('submit',event=>{
    if(event.target.id!=='display-behavior-settings')return;event.preventDefault();
    const data=new FormData(event.target),selected=data.getAll('pages');
    if(data.get('start')===data.get('end')){toast('Choose different start and end times.');return}
    if(selected.length<2){toast('Choose at least two rotation screens.');return}
    const prefs={night:data.has('night'),start:data.get('start'),end:data.get('end'),level:Number(data.get('level')),rotation:data.has('rotation'),dwell:Number(data.get('dwell')),pages:selected,media:data.has('media'),games:data.has('games')};
    displayBehavior.configure(prefs);try{localStorage.setItem('g16-display-behavior',JSON.stringify(displayBehavior.preferences))}catch{}tickDisplayBehavior();toast('Display preferences saved, sir.');
  });
}
setInterval(tickDisplayBehavior,1000);
