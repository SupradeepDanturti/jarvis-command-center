// Registration is owner-only; the browser sends detected IDs, never paths or arguments.
let detectedApps=[],appPickerLoading=false,appPickerPending=false,appPickerLoaded=false,appPickerEpoch=0,appPickerMessage='';
function resetAppSettings(){appPickerEpoch++;detectedApps=[];appPickerLoaded=false;appPickerMessage=''}
function appSettings(){return `<article class="card app-settings"><h2 class="section-title">App shortcuts</h2><div id="app-shortcut-settings">${appSettingsContent()}</div></article>`}
function appSettingsContent(){
  const owner=state.auth?.owner,count=state.apps.length;
  if(!owner)return `<p class="section-note">${count} / 25 apps. Add or remove shortcuts from the approved Windows browser at https://localhost:18761/#system.</p>`;
  const choices=detectedApps.filter(app=>!state.apps.some(saved=>saved.id===app.id));
  return `<p class="section-note">${count} / 25 apps · shared with your tablets</p><label class="app-picker-label" for="app-shortcut-select">Detected Windows apps</label><div class="app-picker"><select id="app-shortcut-select" ${appPickerLoading||appPickerPending||count>=25?'disabled':''}><option value="">${appPickerLoading?'Checking installed apps…':count>=25?'25-app limit reached':choices.length?'Choose an app…':'No more supported apps found'}</option>${choices.map(app=>`<option value="${escapeHtml(app.id)}">${escapeHtml(app.name)}</option>`).join('')}</select><button id="app-shortcut-add" disabled>Add app</button><button id="app-shortcut-refresh" ${appPickerLoading||appPickerPending?'disabled':''}>Detect apps</button></div><p id="app-picker-status" class="section-note" role="status">${escapeHtml(appPickerMessage||'Choose an installed application, sir.')}</p><p class="section-note">Turn Jarvis off and on after changes to update its voice shortcuts.</p><ul class="app-shortcut-list">${state.apps.map(app=>`<li><span>${escapeHtml(app.name)}</span><button data-remove-app="${escapeHtml(app.id)}" aria-label="Remove ${escapeHtml(app.name)} shortcut" ${appPickerPending?'disabled':''}>Remove</button></li>`).join('')}</ul>`;
}
function paintAppSettings(){const root=document.querySelector('#app-shortcut-settings');if(!root)return;const selected=document.querySelector('#app-shortcut-select')?.value;root.innerHTML=appSettingsContent();const select=document.querySelector('#app-shortcut-select');if(select&&[...select.options].some(option=>option.value===selected))select.value=selected;paintAppAdd()}
function paintAppAdd(){const button=document.querySelector('#app-shortcut-add');if(button)button.disabled=appPickerPending||appPickerLoading||state.apps.length>=25||!document.querySelector('#app-shortcut-select')?.value}
async function loadDetectedApps(force=false){
  if(!state.paired||!state.auth?.owner||appPickerLoading||appPickerLoaded&&!force)return;
  appPickerLoading=true;const epoch=appPickerEpoch;paintAppSettings();
  try{const apps=await api('/api/apps/detected',{signal:AbortSignal.timeout(16000)});if(!state.paired||epoch!==appPickerEpoch)return;detectedApps=apps;appPickerLoaded=true;appPickerMessage=apps.length?'Which application shall I add, sir?':'No further supported apps found, sir.'}
  catch(error){if(epoch===appPickerEpoch)appPickerMessage=error.message}
  finally{appPickerLoading=false;paintAppSettings()}
}
document.addEventListener('change',event=>{if(event.target.id==='app-shortcut-select')paintAppAdd()});
document.addEventListener('click',async event=>{
  const button=event.target.closest('#app-shortcut-add,#app-shortcut-refresh,[data-remove-app]');if(!button||appPickerPending||!state.auth?.owner)return;
  if(button.id==='app-shortcut-refresh'){await loadDetectedApps(true);return}
  const id=button.dataset.removeApp||document.querySelector('#app-shortcut-select')?.value;if(!id)return;
  const epoch=appPickerEpoch;appPickerPending=true;paintAppSettings();
  try{const apps=await api(button.dataset.removeApp?`/api/apps/shortcuts/${encodeURIComponent(id)}`:'/api/apps/shortcuts',button.dataset.removeApp?{method:'DELETE'}:{method:'POST',body:JSON.stringify({id})});if(!state.paired||epoch!==appPickerEpoch)return;state.apps=apps;appPickerLoaded=false;appPickerMessage=button.dataset.removeApp?'Shortcut removed, sir.':'App added, sir. It awaits you on Apps.';toast(appPickerMessage);if(state.page==='home'||state.page==='apps')render();await loadDetectedApps(true)}
  catch(error){if(epoch===appPickerEpoch){appPickerMessage=error.message;toast(error.message)}}
  finally{appPickerPending=false;paintAppSettings()}
});
