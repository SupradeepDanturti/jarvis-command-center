// Owner-only personal surfaces. Never store account data or credentials in browser storage.
const assistantPages = ['connections','personalization','agenda','memory','sheets'];
let assistantEpoch = 0, assistantPoll;
function resetAssistant(clear=true){assistantEpoch++;clearTimeout(assistantPoll);if(clear)document.querySelector('#assistant-private')?.replaceChildren()}
function assistantScreen(){
  if(!state.auth?.owner)return '<section class="assistant-surface"><span class="surface-overline">PERSONAL ASSISTANT</span><h2>On your PC,<br><i>sir.</i></h2><p>Open Jarvis at https://localhost:18761 in your approved PC browser to manage personal connections and your agenda.</p></section>';
  const lead={connections:['Your world,<br><i>connected.</i>','Choose what Jarvis can reach.'],personalization:['At <i>your</i><br>service.','Set the details that shape your daily briefing.'],agenda:['Your day,<br><i>in view.</i>','Your primary Google calendar, checked when you ask.'],memory:['Known,<br><i>by you.</i>','Your memories, visible and editable.'],sheets:['Your work,<br><i>in order.</i>','Find your sheets. Review every change.']}[state.page];
  let body='';
  if(state.page==='connections')body=`<div class="assistant-controls"><div class="assistant-heading"><h3>Personal assistant</h3><button data-assistant-toggle disabled>Loading…</button></div><p>Account access starts off each time the server starts. This switch is separate from microphone listening.</p><div class="assistant-heading"><h3>Google account</h3><span id="assistant-account">Not connected</span></div><p>Reads today’s calendar and finds, reads and prepares changes to your spreadsheets when you ask. Dashboard reads stay on the PC; voice tools use personal-context consent in Memory.</p><div class="page-actions"><button data-google-connect disabled>Connect Google</button><button data-google-disconnect disabled>Disconnect from this PC</button></div><p id="assistant-notice" role="status"></p><p id="assistant-sheets-state" role="status"></p><details class="assistant-setup"><summary>Set up Google access</summary><ol><li>Open <a href="https://console.cloud.google.com/" target="_blank" rel="noopener noreferrer">Google Cloud Console</a> and create or select a project.</li><li>Enable the Google Calendar API, Google Sheets API and Google Drive API.</li><li>In Google Auth Platform, set up Branding and Audience. For personal testing, add your Google account as a test user.</li><li>Under Clients, create an OAuth client with application type <strong>Desktop app</strong>, then download its JSON file.</li><li>Choose that file below. Enable the personal assistant, then select Connect Google and finish sign-in in the new tab.</li></ol><label class="assistant-field">Google Desktop client file<input id="google-client-file" type="file" accept="application/json,.json"></label><p>The file is encrypted on your PC after import. Keep the downloaded original private. Testing access normally expires after seven days; reconnect when needed.</p><button data-google-remove-client>Remove saved client and connection</button></details><div class="assistant-planned"><p><strong>Gmail</strong> · Coming in a later connection milestone.</p><p><strong>Google Health</strong> · Waiting for Google’s API onboarding access.</p></div><p class="section-note">Disconnect removes local tokens. To revoke Google’s grant too, remove Jarvis in <a href="https://myaccount.google.com/connections" target="_blank" rel="noopener noreferrer">your Google account connections</a>. No background schedules are active in this build.</p></div>`;
  if(state.page==='personalization')body=`<form id="assistant-profile" class="assistant-controls"><label class="assistant-field">How should the briefing address you?<input name="address" maxlength="40" autocomplete="off" disabled placeholder="sir"><small>Leave blank to omit a form of address.</small></label><label class="assistant-field">Your timezone<input name="timezone" maxlength="80" autocomplete="off" disabled placeholder="America/Toronto"><small>Use a city timezone, such as America/Toronto or Asia/Kolkata.</small></label><label class="assistant-field">Briefing style<select name="tone" disabled><option value="jarvis">Jarvis · concise and composed</option><option value="plain">Plain · direct and simple</option></select></label><div class="page-actions"><button type="submit" disabled>Save preferences</button><button type="button" data-assistant-forget>Forget preferences</button></div><p id="assistant-profile-note" role="status">Loading your preferences…</p><p class="section-note">These preferences are saved privately on your PC and used for the agenda briefing. Saved facts are editable in Memory. With personal-context consent, these preferences also shape Jarvis’s voice replies. Specialist agents and background responsibilities are still to come.</p></form>`;
  if(state.page==='agenda')body=`<div class="assistant-controls"><div class="page-actions"><button class="primary" data-assistant-today disabled>Brief me for today</button><button data-go="connections">Connections</button><button data-go="personalization">Personalization</button></div><p id="assistant-notice" role="status">Loading connection status…</p><div id="assistant-agenda" aria-live="polite"></div><a class="surface-link" href="https://calendar.google.com/" target="_blank" rel="noopener noreferrer">Open Google Calendar</a></div>`;
  if(state.page==='memory')body=memoryBody();
  if(state.page==='sheets')body=sheetsBody();
  return `<section id="assistant-private" class="assistant-surface"><div class="assistant-intro"><span class="surface-overline">JARVIS / PERSONAL ASSISTANT</span><h2>${lead[0]}</h2><p>${lead[1]}</p><div class="assistant-links"><button data-go="agenda">Today</button><button data-go="sheets">Sheets</button><button data-go="memory">Memory</button><button data-go="connections">Connections</button><button data-go="personalization">Personalization</button></div></div>${body}</section>`;
}
function paintAssistantStatus(value){
  const sheetState=document.querySelector('#assistant-sheets-state');if(sheetState)sheetState.textContent=value.sheetsReady?(value.sheetSearchReady?'Sheets and discovery permissions granted. Choose access in More → Sheets.':'Sheets permission granted. Reconnect Google for Drive discovery.'):'Reconnect Google to grant Sheets permission.';
  const toggle=document.querySelector('[data-assistant-toggle]');
  if(toggle){toggle.disabled=false;toggle.dataset.enabled=String(value.enabled);toggle.textContent=value.enabled?'Stop assistant':'Enable assistant'}
  const account=document.querySelector('#assistant-account');if(account)account.textContent=value.account?.email||'Not connected';
  const connect=document.querySelector('[data-google-connect]');if(connect){connect.disabled=!value.enabled||!value.clientConfigured||value.connecting;connect.textContent=value.connecting?'Waiting for Google sign-in…':value.account?'Reconnect Google':'Connect Google'}
  const disconnect=document.querySelector('[data-google-disconnect]');if(disconnect)disconnect.disabled=!value.account&&!value.connecting;
  const today=document.querySelector('[data-assistant-today]');if(today)today.disabled=!value.enabled||!value.calendarReady||!value.account||value.connecting;
  const notice=document.querySelector('#assistant-notice');if(notice)notice.textContent=value.message||(!value.enabled?'Enable personal assistant access in Connections.':!value.account?'Connect Google in Connections first.':!value.calendarReady?'Calendar permission was not granted. Reconnect Google.':'Your calendar is ready, sir.');
}
async function mountAssistant(){
  resetAssistant(false);
  if(!assistantPages.includes(state.page)||!state.auth?.owner||!state.paired)return;
  const epoch=assistantEpoch;
  try{
    const value=await api('/api/assistant/status',{signal:AbortSignal.timeout(12000)});
    if(epoch!==assistantEpoch||!state.paired||!state.auth?.owner)return;
    paintAssistantStatus(value);
    await loadPrivateSurface(epoch);
    if(epoch!==assistantEpoch)return;
    if(state.page==='personalization'){
      const profile=await api('/api/assistant/profile');if(epoch!==assistantEpoch)return;
      const form=document.querySelector('#assistant-profile');
      for(const name of ['address','timezone','tone']){form.elements[name].value=profile[name];form.elements[name].disabled=false}
      form.querySelector('[type=submit]').disabled=false;document.querySelector('#assistant-profile-note').textContent='Your saved briefing preferences.';
    }
    if(value.connecting)assistantPoll=setTimeout(()=>pollAssistant(epoch),1500);
  }catch(error){if(epoch===assistantEpoch)toast(error.message)}
}
async function pollAssistant(epoch){
  if(epoch!==assistantEpoch||!state.paired||!state.auth?.owner||!assistantPages.includes(state.page))return;
  try{const value=await api('/api/assistant/status');if(epoch!==assistantEpoch)return;paintAssistantStatus(value);if(value.connecting)assistantPoll=setTimeout(()=>pollAssistant(epoch),1500)}catch(error){if(epoch===assistantEpoch)toast(error.message)}
}
function paintAgenda(value){
  const root=document.querySelector('#assistant-agenda');if(!root)return;
  const clock=stamp=>new Date(stamp).toLocaleTimeString([],{timeZone:value.timezone,hour:'numeric',minute:'2-digit'});
  root.innerHTML=`<p class="assistant-briefing">${escapeHtml(value.message)}</p><p class="section-note">${escapeHtml(value.day)} · ${escapeHtml(value.timezone)} · Primary calendar</p><ol class="assistant-events">${value.events.map(event=>`<li><time>${escapeHtml(event.allDay?'All day':clock(event.start)+' – '+clock(event.end))}</time><span>${escapeHtml(event.title)}</span></li>`).join('')}</ol>`;
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-assistant-toggle],[data-google-connect],[data-google-disconnect],[data-google-remove-client],[data-assistant-forget],[data-assistant-today]');
  if(!button||!state.auth?.owner||!state.paired)return;
  const epoch=assistantEpoch;button.disabled=true;
  try{
    if(button.hasAttribute('data-assistant-toggle')){paintAssistantStatus(await api('/api/assistant/enabled',{method:'POST',body:JSON.stringify({enabled:button.dataset.enabled!=='true'})}));toast(button.dataset.enabled==='true'?'Personal assistant enabled.':'Personal assistant stopped.')}
    if(button.hasAttribute('data-google-connect')){
      // Reserve an external tab during the click, before awaiting the owner-authorized flow.
      const tab=window.open('about:blank','_blank');
      try{if(!tab)throw new Error('Allow a new tab for Google sign-in, then try again.');tab.opener=null;const result=await api('/api/assistant/google/connect',{method:'POST'});const url=new URL(result.url);if(url.origin!=='https://accounts.google.com'||url.pathname!=='/o/oauth2/v2/auth')throw new Error('Google sign-in address was invalid.');if(epoch!==assistantEpoch){tab.close();return}tab.location.replace(url.href);await pollAssistant(epoch)}catch(error){tab?.close();throw error}
    }
    if(button.hasAttribute('data-google-disconnect')||button.hasAttribute('data-google-remove-client')){const result=await api(button.hasAttribute('data-google-remove-client')?'/api/assistant/google/client':'/api/assistant/google/connection',{method:'DELETE'});if(epoch===assistantEpoch){paintAssistantStatus(result);document.querySelector('#assistant-agenda')?.replaceChildren();toast('Google disconnected from this PC.')}}
    if(button.hasAttribute('data-assistant-forget')){await api('/api/assistant/profile',{method:'DELETE'});if(epoch===assistantEpoch){await mountAssistant();toast('Personal preferences forgotten.')}}
    if(button.hasAttribute('data-assistant-today')){document.querySelector('#assistant-agenda')?.replaceChildren();const result=await api('/api/assistant/today',{method:'POST',signal:AbortSignal.timeout(25000)});if(epoch===assistantEpoch){document.querySelector('#assistant-notice').textContent='Calendar checked.';paintAgenda(result)}}
  }catch(error){if(epoch===assistantEpoch){document.querySelector('#assistant-agenda')?.replaceChildren();toast(error.message)}}finally{if(button.isConnected&&epoch===assistantEpoch){if(button.hasAttribute('data-google-connect'))await pollAssistant(epoch);else button.disabled=false}}
});
document.addEventListener('change',async event=>{
  if(event.target.id!=='google-client-file'||!state.auth?.owner||!state.paired)return;
  const input=event.target,file=input.files?.[0],epoch=assistantEpoch;input.disabled=true;
  try{if(!file||file.size>10000)throw new Error('Choose the downloaded Google Desktop client JSON (under 10 KB).');const contents=await file.text();const value=await api('/api/assistant/google/client',{method:'PUT',body:JSON.stringify({contents})});if(epoch===assistantEpoch){paintAssistantStatus(value);toast('Google client saved.')}}catch(error){if(epoch===assistantEpoch)toast(error.message)}finally{input.value='';input.disabled=false}
});
document.addEventListener('submit',async event=>{
  if(event.target.id!=='assistant-profile')return;event.preventDefault();if(!state.auth?.owner||!state.paired)return;
  const form=event.target,epoch=assistantEpoch,button=form.querySelector('[type=submit]');button.disabled=true;
  try{const profile=Object.fromEntries(['address','timezone','tone'].map(name=>[name,form.elements[name].value]));await api('/api/assistant/profile',{method:'PUT',body:JSON.stringify(profile)});if(epoch===assistantEpoch){document.querySelector('#assistant-profile-note').textContent='Preferences saved.';toast('Personal preferences saved.')}}catch(error){if(epoch===assistantEpoch)toast(error.message)}finally{button.disabled=false}
});
