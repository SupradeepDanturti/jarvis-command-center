// Scheduling belongs to the laptop. This browser renders state and explicit controls.
let restState=null,restReceipt=0,restPending=false,restPreparing=false,restBrightUntil=0;
function restReady(){return deskControlsReady()&&restState&&performance.now()-restReceipt<5000}
function acceptRest(data){
  if(!data||!Number.isInteger(data.revision)||!Number.isFinite(data.serverTime)||!/^\w{24}$/.test(data.instance||''))return;
  if(restState?.instance===data.instance&&(data.revision<restState.revision||data.revision===restState.revision&&data.serverTime<restState.serverTime))return;
  const changed=!!restState?.rest!==!!data.rest;restState=data;restReceipt=performance.now();
  if(changed&&state.paired)render();paintRest();
}
function clearRest(){restState=null;restReceipt=0;restBrightUntil=0;document.body.classList.remove('rest-mode','rest-controls-bright');for(const id of ['alarm-editor','alarm-ringing'])document.querySelector(`#${id}`)?.close();document.querySelector('#alarm-spoken-label').textContent='';paintRest()}
async function loadRest(){try{acceptRest(await api('/api/alarms',{signal:AbortSignal.timeout(6000)}))}catch(error){if(state.paired)toast(error.message)}}
function restSettings(){return `<section class="desk-settings"><h3>Rest & alarms</h3><p class="section-note">Turn off desk monitors, keep a dim tablet clock, and wake to a local spoken alarm.</p><button data-go="rest">Open Rest & alarms</button></section>`}
function restAlarmScreen(){return `<article class="desk-screen rest-alarm-screen">
  <div class="screen-kicker"><span>G16 / REST & ALARMS</span><span data-rest-phase>READY FOR A QUIETER DESK</span></div>
  <div class="rest-composition"><span class="surface-overline" data-rest-greeting>A MOMENT TO REST</span><div class="rest-clock" data-rest-clock role="timer" aria-live="off"></div><p class="rest-date" data-rest-date></p><div class="rest-next"><span class="surface-overline">NEXT ALARM</span><strong data-rest-next>No alarm set</strong><p data-rest-label></p><small data-rest-countdown></small></div></div>
  <p data-rest-message class="reading-detail"></p><div class="rest-actions"><button class="primary" data-enter-rest>Enter Rest mode</button><button data-wake-displays>Wake laptop displays</button><button data-alarm-editor>Set alarm</button><button data-alarm-command="cancel">Cancel alarm</button><button data-rest-brighten>Brighten controls</button></div>
  <div class="screen-bottom"><p class="section-note rest-help">Laptop stays awake. Tablet brightness remains under Android's control.</p>${screenActions()}</div><button class="exit-immersive" data-screen-exit>${glyph('arrow')}<span>Back to display</span></button></article>`}
function localAlarmDate(date){const pad=value=>String(value).padStart(2,'0');return {day:`${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`,time:`${pad(date.getHours())}:${pad(date.getMinutes())}`}}
function openAlarmEditor(){
  const dialog=document.querySelector('#alarm-editor'),form=dialog.querySelector('form');
  const alarm=restState?.alarm,now=Date.now(),date=new Date(alarm?.dueAt*1000>now?alarm.dueAt*1000:now+120000),local=localAlarmDate(date);
  form.elements.day.value=local.day;form.elements.time.value=local.time;form.elements.label.value=alarm?.label||'wake up';
  form.elements.speech.checked=alarm?alarm.speech:!!restState?.audio.ready;
  document.querySelector('#alarm-form-error').textContent='';dialog.showModal();restBrightUntil=performance.now()+15000;paintRest();
}
function paintRest(){
  const data=restState,alarm=data?.alarm,fresh=restReady(),active=state.paired&&!!data?.rest;
  document.body.classList.toggle('rest-mode',active);document.body.classList.toggle('rest-controls-bright',performance.now()<restBrightUntil);
  const now=new Date(),time=now.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:screenPreferences.format==='12'});
  document.querySelectorAll('[data-rest-clock]').forEach(el=>el.textContent=time);
  document.querySelectorAll('[data-rest-date]').forEach(el=>el.textContent=now.toLocaleDateString([],{weekday:'long',month:'long',day:'numeric'}));
  document.querySelectorAll('[data-rest-phase]').forEach(el=>el.textContent=active?'REST MODE':alarm?.status==='armed'?'ALARM ARMED':'READY FOR A QUIETER DESK');
  document.querySelectorAll('[data-rest-next]').forEach(el=>el.textContent=alarm?new Date(alarm.dueAt*1000).toLocaleString([],{weekday:'short',hour:'2-digit',minute:'2-digit'}):'No alarm set');
  document.querySelectorAll('[data-rest-label]').forEach(el=>el.textContent=alarm?.label||'Set a time when you are ready.');
  const serverNow=(data?.serverTime||Date.now())/1000+(performance.now()-restReceipt)/1000,seconds=Math.max(0,(alarm?.dueAt||0)-serverNow);
  document.querySelectorAll('[data-rest-countdown]').forEach(el=>el.textContent=alarm?.status==='armed'?`${Math.floor(seconds/3600)}h ${Math.floor(seconds%3600/60)}m until your alarm`:alarm?{ringing:'Alarm active',missed:'Missed · set a new time',paused:'Paused · review the time',dismissed:'Dismissed'}[alarm.status]||'':'');
  document.querySelectorAll('[data-rest-message]').forEach(el=>el.textContent=restPreparing?'Checking desk monitors through your dock…':!fresh?'Reconnect to control Rest mode and your laptop alarm.':data?.message||(data?.keepingAwake?'Laptop stays awake for Rest mode or your armed alarm.':'Your laptop uses its normal sleep settings.'));
  document.querySelectorAll('[data-enter-rest]').forEach(button=>{button.hidden=active;button.disabled=!fresh||restPending||!data.displayAvailable||alarm?.status==='ringing'});
  document.querySelectorAll('[data-wake-displays],[data-alarm-editor],[data-alarm-command]').forEach(button=>{button.disabled=!fresh||restPending;if(button.dataset.alarmCommand==='cancel')button.hidden=!alarm});
  document.querySelectorAll('[data-rest-brighten]').forEach(button=>button.hidden=!active);
  const editor=document.querySelector('#alarm-editor');editor.querySelector('[type=submit]').disabled=!fresh||restPending;
  document.querySelector('[data-alarm-preview]').disabled=!fresh||restPending||!data?.audio.ready||alarm?.status==='ringing';
  if(restPreparing)document.querySelectorAll('[data-enter-rest],[data-wake-displays],[data-alarm-editor],[data-alarm-command]').forEach(button=>button.disabled=true);
  document.querySelector('#alarm-voice-help').textContent=data?.audio.ready?'Uses your selected Jarvis speaker. Voice only, with no microphone; scheduled audio can play while Windows is locked.':'Jarvis alarm voice is not installed. Leave announcement off for a visual alarm.';
  const ring=document.querySelector('#alarm-ringing');
  if(state.paired&&fresh&&alarm?.status==='ringing'&&document.visibilityState==='visible'){
    editor.close();document.querySelector('#alarm-spoken-label').textContent=`Sir, it's time to ${alarm.label}.`;
    document.querySelector('#alarm-audio-status').textContent=alarm.speech?(data.audio.message||'Alarm voice preparing.'):'Your visual alarm is active.';
    if(!ring.open)ring.showModal();
  }else if(ring.open)ring.close();
}
async function changeRest(url,method,body){
  if(!restReady()||restPending)return;
  restPending=true;paintRest();
  try{const result=await api(url,{method,body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(6000)});acceptRest(result);return true}
  catch(error){toast(error.message);document.querySelector('#alarm-form-error').textContent=error.message;await loadRest();return false}
  finally{restPending=false;paintRest()}
}
function installRestAlarms(){
  document.querySelector('#alarm-ringing').addEventListener('cancel',event=>event.preventDefault());
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-enter-rest],[data-wake-displays],[data-alarm-editor],[data-alarm-command],[data-alarm-close],[data-rest-brighten],[data-alarm-preview]');if(!button||button.disabled)return;
    if(button.hasAttribute('data-rest-brighten')){restBrightUntil=performance.now()+15000;paintRest();return}
    if(button.hasAttribute('data-alarm-close')){document.querySelector('#alarm-editor').close();return}
    if(button.hasAttribute('data-alarm-editor')){openAlarmEditor();return}
    if(button.hasAttribute('data-enter-rest')){
      if(!restReady()||restPending||restPreparing||!confirm('Turn off your DDC/CI desk monitors and dim this tablet? The laptop stays awake and Jarvis listening stops. Wake laptop displays will restore the screens.'))return;
      restPreparing=true;paintRest();
      try{const prepared=await api('/api/rest/prepare',{method:'POST',signal:AbortSignal.timeout(22000)});await changeRest('/api/rest/enter','POST',{nonce:prepared.nonce,revision:restState.revision})}catch(error){toast(error.name==='TimeoutError'?'Monitor check timed out. No monitor-off request was sent.':error.message)}finally{restPreparing=false;paintRest()}return;
    }
    if(button.hasAttribute('data-alarm-preview')){await changeRest('/api/alarms/preview','POST');return}
    if(button.hasAttribute('data-wake-displays')){await changeRest('/api/rest/wake','POST');return}
    if(button.dataset.alarmCommand)await changeRest('/api/alarms/command','POST',{revision:restState.revision,action:button.dataset.alarmCommand});
  });
  document.querySelector('#alarm-form').addEventListener('submit',async event=>{
    event.preventDefault();if(!restReady()||restPending)return;
    const form=event.target,date=new Date(`${form.elements.day.value}T${form.elements.time.value}:00`),local=localAlarmDate(date);
    if(!Number.isFinite(date.getTime())||local.day!==form.elements.day.value||local.time!==form.elements.time.value){document.querySelector('#alarm-form-error').textContent='Choose a valid local time. This time may not exist during a clock change.';return}
    if(restState.alarm?.status==='ringing')return;
    if(await changeRest('/api/alarms','PUT',{revision:restState.revision,dueAt:date.getTime()/1000,label:form.elements.label.value.trim(),speech:form.elements.speech.checked})){document.querySelector('#alarm-editor').close();toast('Alarm saved on your laptop.');}
  });
  document.addEventListener('visibilitychange',paintRest);
}
setInterval(paintRest,500);
