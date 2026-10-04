// Jarvis is a laptop service. This screen never requests browser microphone access.
let voiceState=null, voicePolling=false, voicePending=false, voiceInputLoading=false,voiceHistoryRows=[],voiceHistoryCursor=null,voiceHistoryLoading=false,voiceHistoryMark=null;
function voiceScreen(){
  return `<section class="voice-surface"><div class="voice-intro"><span class="surface-overline">JARVIS / AT YOUR SERVICE</span><div class="jarvis-identity">${jarvisCore()}<div><span class="jarvis-overline">JUST A RATHER VERY INTELLIGENT SYSTEM</span><h2>J.A.R.V.I.S.</h2><p>At your service, sir.<br>Say “Jarvis”, pause, then ask.</p></div></div><div class="voice-history"><div class="voice-history-heading"><h4>Your conversations</h4><span>Saved on this PC</span></div><div id="voice-history-list" role="log" aria-live="polite"></div><div class="voice-history-actions"><button id="voice-history-older" hidden>Earlier conversations</button>${state.auth?.owner?'<button id="voice-history-clear">Clear history</button>':''}</div></div></div><div class="voice-console"><span class="surface-overline">VOICE LINK / CONTROL</span><h3 id="voice-phase">One moment, sir…</h3><p id="voice-message" role="status" aria-live="polite">Checking the voice connection, sir.</p><div class="voice-input"><label for="voice-input">PC microphone</label><select id="voice-input"><option value="">Auto · PC microphone</option></select><button data-voice-refresh type="button" aria-label="Refresh PC microphones">↻</button></div><div class="voice-input"><label for="voice-output">Jarvis speaker</label><select id="voice-output"><option value="">Auto · built-in speakers</option></select></div><div class="voice-input"><label for="voice-followup">Follow-up listening</label><select id="voice-followup"><option value="0">Off · wake phrase each turn</option><option value="15" selected>15 seconds after a reply</option><option value="30">30 seconds after a reply</option></select></div><div class="voice-actions"><button id="voice-toggle" disabled>Turn on Jarvis</button><button id="voice-preview" disabled>Preview voice</button></div><div class="voice-alert-setting"><button id="voice-alert-toggle" type="button" aria-pressed="true">Alerts on</button><small>CPU / RAM 90% · GPU 70°C<br>Once per hour</small></div><p class="voice-caption">PC microphone. Dedicated speaker output. Pauses on Windows lock; starts off after a restart.</p><div class="voice-setup"><h4>OpenAI connection</h4><p id="voice-key-status">Checking connection…</p>${state.auth?.owner?`<details id="voice-key-details" open><summary>Manage API key</summary><form id="voice-key-form" autocomplete="off"><label for="voice-api-key">API key</label><div class="voice-key-entry"><input id="voice-api-key" type="password" autocomplete="off" spellcheck="false" placeholder="Paste your API key here" required aria-describedby="voice-key-help"><button type="submit">Save key</button></div></form><p id="voice-key-help">Encrypted for your Windows account. Never stored in this browser. OpenAI API billing is separate.</p><button id="voice-delete-key" hidden>Remove saved key</button></details>`:`<p>Save or remove the key on the approved Windows browser at https://localhost:18761/#voice.</p>`}<p id="voice-install-status"></p><a class="voice-guide" href="/static/jarvis-help.html" target="_blank" rel="noopener">Setup & supported commands ↗</a></div></div></section>`;
}
function paintVoice(){
  paintJarvisHome();
  const status=voiceState;if(!status)return;
  const mic=document.querySelector('#voice-input');if(mic){if(!mic.matches(':focus'))mic.value=status.inputId||'';mic.disabled=voicePending||status.busy}
  const output=document.querySelector('#voice-output');if(output){if(!output.matches(':focus'))output.value=status.outputId||'';output.disabled=voicePending||status.busy}
  if(!document.querySelector('#voice-phase'))return;
  const alerts=document.querySelector('#voice-alert-toggle');alerts.textContent=status.alertsEnabled!==false?'Alerts on':'Alerts off';alerts.setAttribute('aria-pressed',String(status.alertsEnabled!==false));alerts.disabled=voicePending;
  const followup=document.querySelector('#voice-followup');followup.value=String(status.followupSeconds??15);followup.disabled=voicePending||status.busy;
  paintVoiceHistory();
  const phases={alert:'System alert.',off:'Standing by, sir.',starting:'Waking up.',listening:'At your service, sir.',recording:'Listening, sir.',transcribing:'One moment.',thinking:'On it.',speaking:'Speaking.',followup:'Your turn, sir.',locked:'Paused.',preview:'Meet Jarvis.',error:'Needs attention.'};
  document.querySelector('#voice-phase').textContent=phases[status.phase]||'Standing by.';
  document.querySelector('#voice-message').textContent=status.message;
  const toggle=document.querySelector('#voice-toggle');toggle.textContent=status.busy?'Turn off Jarvis':'Turn on Jarvis';toggle.disabled=voicePending||(!status.busy&&!status.ready);toggle.setAttribute('aria-pressed',String(status.enabled));
  document.querySelector('#voice-preview').disabled=voicePending||status.busy||!status.modelsInstalled||!status.dependenciesInstalled;
  document.querySelector('.voice-surface').dataset.phase=status.phase;

  document.querySelector('#voice-key-status').textContent=status.keyConfigured?'API key saved on your PC.':'An OpenAI API key is needed to understand commands.';
  document.querySelector('#voice-delete-key')?.toggleAttribute('hidden',!status.keyConfigured);
  document.querySelector('#voice-install-status').textContent=status.modelsInstalled&&status.dependenciesInstalled?'Local Jarvis voice and wake word are installed.':'The PC needs the optional voice components. Follow the setup guide below.';
  const keyDetails=document.querySelector('#voice-key-details');if(keyDetails&&keyDetails.dataset.configured!==String(status.keyConfigured)){keyDetails.open=!status.keyConfigured;keyDetails.dataset.configured=String(status.keyConfigured)}
}
async function refreshVoice(){
  if(voicePolling||!state.paired||document.visibilityState!=='visible')return;
  voicePolling=true;const epoch=jarvisVisualEpoch;
  try{const status=await api('/api/voice/status',{signal:AbortSignal.timeout(4000)});if(!state.paired||epoch!==jarvisVisualEpoch)return;voiceState=status;jarvisStatusFreshAt=Date.now();const mark=voiceState.history?.at(-1)?.id??null;if(state.page==='voice'&&mark!==voiceHistoryMark){voiceHistoryMark=mark;await loadVoiceHistory()}paintVoice()}
  catch(error){jarvisStatusFreshAt=0;paintJarvisHome();const message=document.querySelector('#voice-message');if(message)message.textContent='I can’t read the voice status, sir. Reconnecting…';document.querySelector('#voice-toggle')?.setAttribute('disabled','');document.querySelector('#voice-preview')?.setAttribute('disabled','')}
  finally{voicePolling=false}
}
document.addEventListener('submit',async event=>{
  if(event.target.id!=='voice-key-form')return;
  event.preventDefault();if(voicePending)return;
  const input=document.querySelector('#voice-api-key'),button=event.target.querySelector('button');
  voicePending=true;button.disabled=true;paintVoice();
  try{await api('/api/voice/key',{method:'PUT',body:JSON.stringify({key:input.value.trim()}),signal:AbortSignal.timeout(5000)});toast('Your key is saved privately on this PC, sir.');}
  catch(error){toast(error.message)}
  finally{input.value='';voicePending=false;button.disabled=false;await refreshVoice();paintVoice()}
});
document.addEventListener('click',async event=>{
  const button=event.target.closest('#voice-toggle,#voice-preview,#voice-delete-key');if(!button||voicePending)return;
  voicePending=true;paintVoice();
  try{
    if(button.id==='voice-delete-key')await api('/api/voice/key',{method:'DELETE'});
    else if(button.id==='voice-preview')voiceState=await api('/api/voice/preview',{method:'POST'});
    else voiceState=await api('/api/voice/enabled',{method:'POST',body:JSON.stringify({enabled:!voiceState?.busy})});
  }catch(error){toast(error.message)}
  finally{voicePending=false;await refreshVoice();paintVoice()}
});
setInterval(refreshVoice,1000);
document.addEventListener('visibilitychange',refreshVoice);

async function loadVoiceInputs(){
  if(voiceInputLoading||!state.paired||!['voice','system'].includes(state.page))return;
  voiceInputLoading=true;
  try{const [devices,outputs]=await Promise.all([api('/api/voice/inputs'),api('/api/voice/outputs')]);const speaker=document.querySelector('#voice-output');if(speaker){speaker.replaceChildren(new Option('Auto · built-in speakers',''),...outputs.map(d=>new Option(d.name,d.id)));speaker.value=voiceState?.outputId||''}const select=document.querySelector('#voice-input');if(select){select.replaceChildren(new Option('Auto · PC microphone',''),...devices.map(d=>new Option(d.name,d.id)));select.value=voiceState?.inputId||''}}
  catch{}finally{voiceInputLoading=false}
}
document.addEventListener('change',async event=>{
  if(event.target.id!=='voice-input'||voicePending)return;
  const selected=event.target.value||null;voicePending=true;paintVoice();
  try{voiceState=await api('/api/voice/input',{method:'PUT',body:JSON.stringify({id:selected})})}
  catch(error){toast(error.message)}finally{voicePending=false;await refreshVoice();paintVoice()}
});

function voiceInputSettings(){return `<div class="detail-row voice-setting"><label for="voice-input">Jarvis microphone</label><select id="voice-input"><option value="">Auto · PC microphone</option></select><button data-voice-refresh type="button" aria-label="Refresh PC microphones">↻</button></div><div class="detail-row voice-setting"><label for="voice-output">Jarvis speaker</label><select id="voice-output"><option value="">Auto · built-in speakers</option></select></div><p class="section-note">Choose the PC input and speaker Jarvis uses. Turn Jarvis off before changing it.</p><div class="page-actions"><button data-go="voice">Open Jarvis</button></div>`}

document.addEventListener('click',event=>{if(event.target.closest('[data-voice-refresh]'))loadVoiceInputs()});

function paintVoiceHistory(){
  const list=document.querySelector('#voice-history-list');if(!list)return;
  const rows=voiceHistoryRows.length?voiceHistoryRows:voiceState?.history||[];
  const signature=rows.map(r=>r.id).join(',');if(list.dataset.signature===signature)return;
  list.dataset.signature=signature;
  const wasAtBottom=list.scrollHeight-list.scrollTop-list.clientHeight<50;
  list.innerHTML=rows.map(row=>`<article class="voice-history-turn"><time>${escapeHtml(new Date(row.created*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}))}</time><p class="voice-human"><span>${row.kind==='alert'?'System':'You'}</span>${escapeHtml(row.heard)}</p><p><span>Jarvis</span>${escapeHtml(row.reply)}${voiceSourceLinks(row.sources)}</p>${row.action?`<small class="voice-tool-trace">${escapeHtml(row.action.name)} ${escapeHtml(JSON.stringify(row.action.arguments))} · ${row.action.ok?'Sent':'Failed'}${row.action.message?' · '+escapeHtml(row.action.message):''}</small>`:''}</article>`).join('')||'<p class="voice-history-empty">Our next conversation will appear here, sir.</p>';
  if(wasAtBottom)list.scrollTop=list.scrollHeight;
  document.querySelector('.voice-surface')?.classList.toggle('has-conversation',rows.length>0);
  document.querySelector('#voice-history-older')?.toggleAttribute('hidden',!voiceHistoryCursor);
}
async function loadVoiceHistory(older=false){
  if(voiceHistoryLoading||!state.paired||state.page!=='voice')return;
  voiceHistoryLoading=true;
  try{const rows=await api(`/api/voice/history${older&&voiceHistoryCursor?'?before='+voiceHistoryCursor:''}`);if(older){const merged=new Map([...rows,...voiceHistoryRows].map(r=>[r.id,r]));voiceHistoryRows=[...merged.values()].sort((a,b)=>a.id-b.id)}else voiceHistoryRows=rows;voiceHistoryCursor=rows.length===50?rows[0].id:null;paintVoiceHistory()}
  catch(error){toast(error.message)}finally{voiceHistoryLoading=false}
}
document.addEventListener('change',async event=>{
  if(event.target.id!=='voice-followup'||voicePending)return;
  const seconds=Number(event.target.value);voicePending=true;paintVoice();
  try{voiceState=await api('/api/voice/followup',{method:'PUT',body:JSON.stringify({seconds})})}
  catch(error){toast(error.message)}finally{voicePending=false;await refreshVoice();paintVoice()}
});
document.addEventListener('click',async event=>{
  if(event.target.closest('#voice-history-older'))await loadVoiceHistory(true);
  if(event.target.closest('#voice-history-clear')){
    if(!confirm('Clear all saved Jarvis conversations from this PC? Jarvis will turn off.'))return;
    try{await api('/api/voice/history',{method:'DELETE'});voiceHistoryRows=[];voiceHistoryMark=null;voiceHistoryCursor=null;await refreshVoice();paintVoiceHistory()}catch(error){toast(error.message)}
  }
});

function voiceSourceLinks(sources){return (sources||[]).slice(0,5).map(source=>{try{const url=new URL(source.url);if(!['http:','https:'].includes(url.protocol)||url.username)return '';return ` <a class="voice-source" href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">[${escapeHtml(source.title||url.hostname)} ↗]</a>`}catch{return ''}}).join('')}

document.addEventListener('change',async event=>{
  if(event.target.id!=='voice-output'||voicePending)return;
  const body={id:event.target.value||null};
  voicePending=true;paintVoice();
  try{voiceState=await api('/api/voice/output',{method:'PUT',body:JSON.stringify(body)})}
  catch(error){toast(error.message)}finally{voicePending=false;await refreshVoice();paintVoice()}
});

document.addEventListener('click',async event=>{
  if(!event.target.closest('#voice-alert-toggle')||voicePending)return;
  const enabled=voiceState?.alertsEnabled===false;voicePending=true;paintVoice();
  try{voiceState=await api('/api/voice/alerts',{method:'PUT',body:JSON.stringify({enabled})})}
  catch(error){toast(error.message)}finally{voicePending=false;await refreshVoice();paintVoice()}
});
