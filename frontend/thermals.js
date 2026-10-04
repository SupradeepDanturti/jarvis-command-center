// Extra readings are selected by the loopback owner from real provider identities.
let thermalInventory=null;
function thermalReadings(){return `<section class="thermal-section"><h2 class="section-title">Temperatures & cooling</h2><p data-thermal-reason class="section-note">Extra sensors off</p><div data-thermal-readings></div><div id="thermal-setup"></div></section>`}
function paintThermals(){
  const data=state.data?.thermals;
  const root=document.querySelector('[data-thermal-readings]');if(!root)return;
  document.querySelector('[data-thermal-reason]').textContent=state.stale?'Readings unavailable while reconnecting.':data?.reason||'Extra sensors off';
  const row=(label,reading)=>`<div class="detail-row"><span>${escapeHtml(label)}</span><strong>${state.stale||!reading?'Unavailable':reading.kind==='flag'?(reading.value?'Yes':'No'):`${format(reading.value)} ${escapeHtml(reading.unit)}`}</strong></div>${reading&&!state.stale?`<p class="sensor-source">${escapeHtml(reading.sensor)} · ${escapeHtml(reading.label)} · ${escapeHtml(reading.source)} · ${escapeHtml(new Date(reading.sampledAt).toLocaleTimeString())}</p>`:''}`;
  root.innerHTML=row('CPU package temperature',data?.cpuTemperature)+row('CPU thermal throttling',data?.cpuThrottle)+row('GPU thermal throttling',data?.gpuThrottle)+(data?.fans?.length?data.fans.map(reading=>row(reading.label,reading)).join(''):row('Fan speed',null))+(data?.drives?.length?data.drives.map(reading=>row(`${reading.sensor} · ${reading.label}`,reading)).join(''):row('SSD temperature',null));
}
async function loadThermalSetup(){
  const root=document.querySelector('#thermal-setup');if(!root)return;
  if(!state.auth?.owner){root.innerHTML='<p class="section-note">Configure extra sensors from the approved localhost browser on your PC.</p>';return}
  try{
    const data=await api('/api/thermals/inventory');if(!root.isConnected)return;thermalInventory=data;
    const settings=data.settings;
    const option=(kind,value)=>'<option value="">Not assigned</option>'+data.readings.filter(reading=>reading.kind===kind).map(reading=>`<option value="${escapeHtml(reading.id)}" ${reading.id===value?'selected':''}>${escapeHtml(reading.sensor)} · ${escapeHtml(reading.label)} (${escapeHtml(reading.unit)})</option>`).join('');
    const checks=(kind,key)=>data.readings.filter(reading=>reading.kind===kind).map(reading=>`<label class="setting-check"><input type="checkbox" name="${key}" value="${escapeHtml(reading.id)}" ${settings[key].includes(reading.id)?'checked':''}>${escapeHtml(reading.sensor)} · ${escapeHtml(reading.label)}</label>`).join('');
    root.innerHTML=`<details class="desk-settings"><summary>Extra sensor setup · Windows owner</summary><p class="section-note">Open HWiNFO Sensors and enable shared memory on this PC. Select verified labels below. No sensor tool is installed automatically; non-Pro shared memory stops after 12 hours.</p><button type="button" id="thermal-enable">${settings.enabled?'Turn extra sensors off':'Turn extra sensors on'}</button><button type="button" id="thermal-refresh">Refresh sensor list</button><p class="section-note">${escapeHtml(data.reason)} · ${data.readings.length} supported readings</p><form id="thermal-settings"><label>CPU package temperature<select name="cpuTemperature">${option('temperature',settings.cpuTemperature)}</select></label><label>CPU thermal throttling<select name="cpuThrottle">${option('flag',settings.cpuThrottle)}</select></label><label>GPU thermal throttling<select name="gpuThrottle">${option('flag',settings.gpuThrottle)}</select></label><fieldset><legend>Fan readings</legend>${checks('fan','fans')||'<p class="section-note">No fan sensor reported.</p>'}</fieldset><fieldset><legend>Physical SSD temperature readings</legend>${checks('temperature','drives')||'<p class="section-note">No temperature sensor reported.</p>'}</fieldset><p class="section-note">Choose only labels confirmed in HWiNFO. Throttling needs an explicit flag; temperatures alone do not establish throttling.</p><button type="submit" ${!settings.enabled?'disabled':''}>Save sensor mapping</button></form></details>`;
  }catch(error){root.textContent=error.message}
}
function installThermals(root){
  root.addEventListener('click',async event=>{
    const button=event.target.closest('#thermal-enable,#thermal-refresh');if(!button)return;
    button.disabled=true;
    try{if(button.id==='thermal-enable'){
      const enabled=!thermalInventory.settings.enabled;
      // Enable/discovery is independent of mappings; stale IDs are never submitted.
      await api('/api/thermals/settings',{method:'PUT',body:JSON.stringify({...thermalInventory.settings,enabled})});
    }await loadThermalSetup()}catch(error){toast(error.message)}finally{button.disabled=false}
  });
  root.addEventListener('submit',async event=>{
    if(event.target.id!=='thermal-settings')return;event.preventDefault();
    const data=new FormData(event.target),button=event.target.querySelector('button[type=submit]');button.disabled=true;
    const body={enabled:true,cpuTemperature:data.get('cpuTemperature')||null,cpuThrottle:data.get('cpuThrottle')||null,gpuThrottle:data.get('gpuThrottle')||null,fans:data.getAll('fans'),drives:data.getAll('drives')};
    try{await api('/api/thermals/settings',{method:'PUT',body:JSON.stringify(body)});toast('Sensor selections saved, sir.');await loadThermalSetup()}catch(error){toast(error.message)}finally{button.disabled=false}
  });
}
