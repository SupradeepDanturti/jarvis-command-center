// Jarvis is a laptop service. This screen never requests browser microphone access.
let voiceState=null, voicePolling=false, voicePending=false, voiceInputLoading=false;
function voiceScreen(){
  return `<section class="voice-surface"><div class="voice-intro"><span class="surface-overline">YOUR LAPTOP. YOUR VOICE.</span><h2>At your<br><i>service.</i></h2><p>Say “Hey Jarvis.” Open YouTube, adjust your sound, or ask how your laptop is doing.</p><div class="voice-orbit" aria-hidden="true"><span>J</span></div></div><div class="voice-console"><span class="surface-overline">JARVIS · LOCAL VOICE</span><h3 id="voice-phase">Connecting…</h3><p id="voice-message" role="status" aria-live="polite">Checking your laptop.</p><div class="voice-input"><label for="voice-input">Laptop microphone</label><select id="voice-input"><option value="">Auto · laptop microphone</option></select><button data-voice-refresh type="button" aria-label="Refresh laptop microphones">↻</button></div><div class="voice-actions"><button id="voice-toggle" disabled>Turn on Jarvis</button><button id="voice-preview" disabled>Preview voice</button></div><p class="voice-caption">Uses the laptop’s microphone and speakers. Pauses while Windows locks or Jarvis speaks. Keeps running when you close this page; starts off after a server restart.</p><div id="voice-exchange" hidden><span class="surface-overline">LAST REQUEST · THIS SESSION</span><p id="voice-heard"></p><p id="voice-reply"></p></div><div class="voice-setup"><h4>OpenAI connection</h4><p id="voice-key-status">Checking connection…</p>${state.auth?.owner?`<form id="voice-key-form" autocomplete="off"><label for="voice-api-key">API key</label><div class="voice-key-entry"><input id="voice-api-key" type="password" autocomplete="off" spellcheck="false" placeholder="Paste your API key here" required aria-describedby="voice-key-help"><button type="submit">Save key</button></div></form><p id="voice-key-help">Encrypted for your Windows account. Never stored in this browser. OpenAI API billing is separate.</p><button id="voice-delete-key" hidden>Remove saved key</button>`:`<p>Save or remove the key on the approved laptop browser at https://localhost:18761/#voice.</p>`}<p id="voice-install-status"></p><a class="voice-guide" href="/static/jarvis-help.html" target="_blank" rel="noopener">Setup & supported commands ↗</a></div></div></section>`;
}
function paintVoice(){
  const status=voiceState;if(!status)return;
  const mic=document.querySelector('#voice-input');if(mic){if(!mic.matches(':focus'))mic.value=status.inputId||'';mic.disabled=voicePending||status.busy}
  if(!document.querySelector('#voice-phase'))return;
  const phases={off:'Standing by.',starting:'Waking up.',listening:'At your service.',recording:'I’m listening.',transcribing:'One moment.',thinking:'On it.',speaking:'Speaking.',locked:'Paused.',preview:'Meet Jarvis.',error:'Needs attention.'};
  document.querySelector('#voice-phase').textContent=phases[status.phase]||'Standing by.';
  document.querySelector('#voice-message').textContent=status.message;
  const toggle=document.querySelector('#voice-toggle');toggle.textContent=status.busy?'Turn off Jarvis':'Turn on Jarvis';toggle.disabled=voicePending||(!status.busy&&!status.ready);toggle.setAttribute('aria-pressed',String(status.enabled));
  document.querySelector('#voice-preview').disabled=voicePending||status.busy||!status.modelsInstalled||!status.dependenciesInstalled;
  document.querySelector('.voice-surface').dataset.phase=status.phase;

  document.querySelector('#voice-key-status').textContent=status.keyConfigured?'API key saved on your laptop.':'An OpenAI API key is needed to understand commands.';
  document.querySelector('#voice-delete-key')?.toggleAttribute('hidden',!status.keyConfigured);
  document.querySelector('#voice-install-status').textContent=status.modelsInstalled&&status.dependenciesInstalled?'Local Jarvis voice and wake word are installed.':'The laptop needs the optional voice components. Follow the setup guide below.';
  document.querySelector('#voice-exchange').hidden=!(status.lastHeard||status.lastReply);
  document.querySelector('#voice-heard').textContent=status.lastHeard?`You: ${status.lastHeard}`:'';
  document.querySelector('#voice-reply').textContent=status.lastReply?`Jarvis: ${status.lastReply}`:'';
}
async function refreshVoice(){
  if(voicePolling||!state.paired||!['voice','system'].includes(state.page)||document.visibilityState!=='visible')return;
  voicePolling=true;
  try{voiceState=await api('/api/voice/status',{signal:AbortSignal.timeout(4000)});paintVoice()}
  catch(error){const message=document.querySelector('#voice-message');if(message)message.textContent='Voice status unavailable. Reconnecting…';document.querySelector('#voice-toggle')?.setAttribute('disabled','');document.querySelector('#voice-preview')?.setAttribute('disabled','')}
  finally{voicePolling=false}
}
document.addEventListener('submit',async event=>{
  if(event.target.id!=='voice-key-form')return;
  event.preventDefault();if(voicePending)return;
  const input=document.querySelector('#voice-api-key'),button=event.target.querySelector('button');
  voicePending=true;button.disabled=true;paintVoice();
  try{await api('/api/voice/key',{method:'PUT',body:JSON.stringify({key:input.value.trim()}),signal:AbortSignal.timeout(5000)});toast('Key saved privately on your laptop.');}
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
  try{const devices=await api('/api/voice/inputs');const select=document.querySelector('#voice-input');if(select){select.replaceChildren(new Option('Auto · laptop microphone',''),...devices.map(d=>new Option(d.name,d.id)));select.value=voiceState?.inputId||''}}
  catch{}finally{voiceInputLoading=false}
}
document.addEventListener('change',async event=>{
  if(event.target.id!=='voice-input'||voicePending)return;
  const selected=event.target.value||null;voicePending=true;paintVoice();
  try{voiceState=await api('/api/voice/input',{method:'PUT',body:JSON.stringify({id:selected})})}
  catch(error){toast(error.message)}finally{voicePending=false;await refreshVoice();paintVoice()}
});

function voiceInputSettings(){return `<div class="detail-row voice-setting"><label for="voice-input">Jarvis microphone</label><select id="voice-input"><option value="">Auto · laptop microphone</option></select><button data-voice-refresh type="button" aria-label="Refresh laptop microphones">↻</button></div><p class="section-note">Choose the laptop input Jarvis uses. Turn Jarvis off before changing it.</p><div class="page-actions"><button data-go="voice">Open Jarvis</button></div>`}

document.addEventListener('click',event=>{if(event.target.closest('[data-voice-refresh]'))loadVoiceInputs()});
