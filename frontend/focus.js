// The PC owns timer state; local monotonic time only animates its last snapshot.
let focusState=null,focusReceipt=0,focusView=false,focusPending=false;
function acceptFocus(data){
  if(!data||!Number.isFinite(data.remaining)||!Number.isInteger(data.revision))return;
  if(focusState&&(data.revision<focusState.revision||(data.revision===focusState.revision&&data.serverTime<focusState.serverTime)))return;
  focusState=data;focusReceipt=performance.now();paintFocus();
}
function focusRemaining(){return Math.max(0,(focusState?.remaining??1500)-(focusState?.status==='running'&&deskControlsReady()?(performance.now()-focusReceipt)/1000:0))}
function focusTime(value){const s=Math.ceil(Math.max(0,value));return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`}
function focusScreen(){return `<article class="desk-screen focus-screen"><div class="screen-kicker"><span>JARVIS / FOCUS</span><button data-clock-mode="clock">Show clock</button></div><div class="focus-composition"><span class="surface-overline" data-focus-phase>FOCUS SESSION</span><div class="focus-countdown" data-focus-countdown role="timer" aria-live="off">25:00</div><p data-focus-message class="reading-detail"></p><div class="focus-controls"><button data-focus-action="start" class="primary">Start</button><button data-focus-action="pause">Pause</button><button data-focus-action="skip">Skip</button><button data-focus-action="reset">Reset</button></div><small data-clock-date></small></div><div class="screen-bottom"><span data-focus-sessions class="reading-detail"></span>${screenActions()}</div><button class="exit-immersive" data-screen-exit><span>Back to display</span></button></article>`}
function focusSettings(){const prefs=focusState?.settings||{focus:25,short:5,long:15,announcements:false};return `<section class="desk-settings"><h3>Focus timer</h3><form id="focus-settings"><div class="settings-fields">${[['focus','Focus'],['short','Short break'],['long','Long break']].map(([key,label])=>`<label>${label} · minutes<input type="number" name="${key}" min="1" max="180" value="${prefs[key]}" required></label>`).join('')}</div><label class="setting-check"><input type="checkbox" name="announcements" ${prefs.announcements?'checked':''}>Jarvis completion announcements</label><p class="section-note">Speech uses your selected speaker while Jarvis is already on and idle. Each phase waits for you to start the next.</p><button type="submit">Save timer settings</button></form><button data-show-focus>Show timer</button></section>`}
function paintFocus(){
  const data=focusState, remaining=focusRemaining();
  document.querySelectorAll('[data-focus-countdown]').forEach(el=>el.textContent=focusTime(remaining));
  document.querySelectorAll('[data-focus-phase]').forEach(el=>el.textContent={focus:'FOCUS SESSION',short:'SHORT BREAK',long:'LONG BREAK'}[data?.phase]||'FOCUS SESSION');
  document.querySelectorAll('[data-focus-message]').forEach(el=>el.textContent=!deskControlsReady()?'Reconnect to control the PC timer.':data?.message||(data?.status==='running'?'One task at a time, sir.':data?.status==='paused'?'Paused, sir. Resume when you’re ready.':'Shall we focus, sir?'));
  document.querySelectorAll('[data-focus-sessions]').forEach(el=>el.textContent=`${data?.completed||0} focus sessions completed`);
  document.querySelectorAll('[data-focus-action]').forEach(button=>{
    let action=button.dataset.focusAction;
    if(['start','resume'].includes(action)){action=data?.status==='paused'?'resume':'start';button.dataset.focusAction=action;button.textContent=data?.status==='complete'?'Start next phase':action==='resume'?'Resume':'Start';button.hidden=data?.status==='running'}
    if(action==='pause')button.hidden=data?.status!=='running';
    button.disabled=!data||!deskControlsReady()||focusPending;
  });
  document.querySelectorAll('[data-focus-shortcut]').forEach(el=>el.textContent=data&&['running','paused','complete'].includes(data.status)?`${data.status==='complete'?'Complete':focusTime(remaining)} · Focus`:'Focus timer');
  const submit=document.querySelector('#focus-settings button[type=submit]');if(submit)submit.disabled=!data||!deskControlsReady()||focusPending;
}
async function loadFocus(){try{acceptFocus(await api('/api/focus'))}catch(error){if(state.paired)toast(error.message)}}
function installFocus(root){
  root.addEventListener('click',async event=>{
    const button=event.target.closest('[data-focus-action],[data-show-focus],[data-clock-mode]');if(!button||button.disabled)return;
    if(button.hasAttribute('data-show-focus')){focusView=true;goPage('clock');return}
    if(button.dataset.clockMode){focusView=button.dataset.clockMode==='focus';render();return}
    if(!focusState||focusPending||!deskControlsReady())return;
    const action=button.dataset.focusAction;
    if(action==='reset'&&['running','paused'].includes(focusState.status)&&!window.confirm('Reset this focus session, sir?'))return;
    focusPending=true;paintFocus();
    try{acceptFocus(await api('/api/focus/command',{method:'POST',body:JSON.stringify({action,revision:focusState.revision}),signal:AbortSignal.timeout(4000)}))}
    catch(error){toast(error.message);await loadFocus()}
    finally{focusPending=false;paintFocus()}
  });
  root.addEventListener('submit',async event=>{
    if(event.target.id!=='focus-settings')return;event.preventDefault();if(!focusState||focusPending||!deskControlsReady())return;
    const form=new FormData(event.target),body={revision:focusState.revision,focus:Number(form.get('focus')),short:Number(form.get('short')),long:Number(form.get('long')),announcements:form.has('announcements')};
    focusPending=true;paintFocus();
    try{acceptFocus(await api('/api/focus/settings',{method:'PUT',body:JSON.stringify(body),signal:AbortSignal.timeout(4000)}));toast('Timer settings saved.')}
    catch(error){toast(error.message);await loadFocus()}
    finally{focusPending=false;paintFocus()}
  });
}
setInterval(paintFocus,250);
