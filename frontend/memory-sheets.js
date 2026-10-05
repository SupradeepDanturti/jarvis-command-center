// Personal state stays in the private PC store. These surfaces keep only transient DOM results.
function memoryBody(){return `<div class="assistant-controls"><h3>What Jarvis knows</h3><p>Add a fact below, or say “Jarvis, remember that I prefer morning meetings.” Suggested memories wait for your approval. Saved facts stay on this PC.</p><label class="assistant-check"><input type="checkbox" id="assistant-cloud" disabled>Use personal context with Jarvis</label><p class="section-note">When enabled, selected saved facts, your preferences and requested Calendar or Sheets results are sent to OpenAI to answer your voice requests. Replies join your existing private conversation history. Credentials stay on the PC. Turn this off to stop personal tools; account data is never saved automatically as a fact.</p><form id="memory-add"><label class="assistant-field">A fact to remember<textarea name="text" maxlength="500" required placeholder="I prefer morning meetings."></textarea></label><button type="submit">Remember this</button></form><div id="memory-list" aria-live="polite"></div><button data-memory-clear>Forget all saved facts</button><p class="section-note">Forgetting facts does not erase earlier conversations. Personal changes stop the active voice session to remove stale context; enable listening again in Jarvis.</p><details class="assistant-setup"><summary>Preferences and working context</summary><p>Each turn uses up to 20 relevant or recent facts and the last 6 conversation exchanges. The last selection below is the input prepared before a voice turn, not hidden model thoughts or a complete transcript of tool calls.</p><pre id="memory-context"></pre><button data-go="personalization">Edit preferences</button><button data-go="voice">View conversation history</button><button data-memory-history>Clear conversation history</button></details><button data-memory-export>Download memory and context</button></div>`}
function sheetsBody(){return `<div class="assistant-controls"><h3>Find your spreadsheets</h3><p>Enable the Google Drive API and Google Sheets API in your Cloud project, then reconnect Google in Connections. Reuse your saved client.</p><label class="assistant-check"><input type="checkbox" id="sheet-discovery" disabled>Let Jarvis find and use my spreadsheets</label><p class="section-note">Allows name searches and access to all tabs in spreadsheets your Google account can open. Google’s metadata permission covers Drive file names and details; Jarvis searches only Google spreadsheets. Edits always wait for your review. Voice access also needs personal context in Memory.</p><p id="sheet-search-state"></p><form id="sheet-search"><label class="assistant-field">Spreadsheet name<input name="query" maxlength="100" placeholder="Planner · leave blank for recent sheets"></label><button type="submit">Find sheets</button><button type="button" data-sheet-search-more hidden>More results</button></form><div id="sheet-search-results" aria-live="polite"></div><details class="assistant-setup"><summary>Or give access to one spreadsheet</summary><form id="sheet-add"><label class="assistant-field">Name<input name="name" maxlength="60" required placeholder="Weekly tracker"></label><label class="assistant-field">Google Sheets link or spreadsheet ID<input name="spreadsheetId" maxlength="300" required autocomplete="off"></label><label class="assistant-field">Access<select name="access"><option value="spreadsheet">Entire spreadsheet · all tabs</option><option value="range">One specific range</option></select></label><label class="assistant-field" id="sheet-range-field" hidden>Range<input name="range" maxlength="220" disabled placeholder="Sheet1!A1:D20"><small>At most 100 rows, 20 columns and 1,000 cells per request.</small></label><button type="submit">Give access</button></form></details><div id="sheet-list"></div><div id="sheet-browser" aria-live="polite"></div><div id="sheet-result" aria-live="polite"></div><h3>Changes to review</h3><p>Each read or edit covers up to 100 rows, 20 columns and 1,000 cells. Whole-spreadsheet access lets you choose any tab and move through its cells. Changes replace only supplied cells; text is written literally. Previews expire after five minutes.</p><div id="sheet-proposals"></div><button data-private-refresh>Refresh</button><p class="section-note">If an update times out, check Google Sheets before submitting again. Jarvis never retries a submitted write automatically.</p></div>`}
let privateSurfaceRevision=0;
async function loadPrivateSurface(epoch){
  const revision=++privateSurfaceRevision;
  if(state.page==='memory'){
    const data=await api('/api/assistant/memory');if(epoch!==assistantEpoch||revision!==privateSurfaceRevision)return;
    const cloud=document.querySelector('#assistant-cloud');cloud.disabled=false;cloud.checked=data.cloudContext;
    document.querySelector('#memory-list').innerHTML=data.facts.length?data.facts.map(fact=>`<form class="memory-edit" data-memory-id="${escapeHtml(fact.id)}"><label class="assistant-field">${fact.pending?'Suggested memory · review before saving':'Saved memory'}<textarea name="text" maxlength="500" required>${escapeHtml(fact.text)}</textarea></label><p class="section-note">${escapeHtml(fact.source)} · ${escapeHtml(new Date(fact.updated*1000).toLocaleString())}</p><div class="page-actions"><button type="submit">${fact.pending?'Approve memory':'Save changes'}</button><button type="button" data-memory-delete="${escapeHtml(fact.id)}">${fact.pending?'Discard':'Forget'}</button></div></form>`).join(''):'<p>No saved facts yet.</p>';
    document.querySelector('#memory-context').textContent=JSON.stringify({preferences:data.profile,lastSelection:data.lastContext,currentRecentConversation:data.recentConversation,limits:data.limits},null,2);
  }
  if(state.page==='sheets'){
    const data=await api('/api/assistant/sheets');if(epoch!==assistantEpoch||revision!==privateSurfaceRevision)return;
    const discovery=document.querySelector('#sheet-discovery');discovery.disabled=false;discovery.checked=!!data.discoveryEnabled;
    document.querySelector('#sheet-search-state').textContent=data.discoveryReady?'Drive discovery permission granted.':'Reconnect Google to grant Drive metadata permission for discovery.';
    document.querySelector('#sheet-search [type=submit]').disabled=!data.discoveryEnabled;
    document.querySelector('#sheet-list').innerHTML=data.sheets.map(sheet=>`<div class="memory-edit"><h3>${escapeHtml(sheet.name)}</h3><p>${sheet.access==='spreadsheet'?'Entire spreadsheet · all tabs':escapeHtml(sheet.range)}</p><div class="page-actions"><button ${sheet.access==='spreadsheet'?'data-sheet-explore':'data-sheet-read'}="${escapeHtml(sheet.id)}">${sheet.access==='spreadsheet'?'Explore tabs':'Read range'}</button><button data-sheet-delete="${escapeHtml(sheet.id)}">Remove access</button></div></div>`).join('')||'<p>No individual spreadsheets registered. Discovery works without registration.</p>';
    document.querySelector('#sheet-proposals').innerHTML=data.proposals.map(proposal=>`<div class="memory-edit"><h4>${escapeHtml(proposal.sheet.name)}</h4><p>${escapeHtml(proposal.sheet.spreadsheetId)}<br>${escapeHtml(proposal.sheet.range)}<br>Expires ${escapeHtml(new Date(proposal.expiresAt*1000).toLocaleTimeString())}</p>${sheetPreview(proposal.values)}<div class="page-actions"><button data-sheet-apply="${escapeHtml(proposal.id)}">Apply these values</button><button data-sheet-discard="${escapeHtml(proposal.id)}">Discard</button></div></div>`).join('')||'<p>No pending changes.</p>';
  }
}
document.addEventListener('change',async event=>{
  if(event.target.matches('#sheet-browse [name=tab]')){const form=event.target.form,tab=JSON.parse(form.dataset.tabs)[Number(event.target.value)];form.elements.row.max=tab.rows;form.elements.column.max=tab.columns;form.elements.row.value=1;form.elements.column.value=1;privateSurfaceRevision++;document.querySelector('#sheet-result').replaceChildren();return}
  if(event.target.matches('#sheet-add [name=access]')){const full=event.target.value==='spreadsheet',input=document.querySelector('#sheet-add [name=range]');input.disabled=full;input.required=!full;document.querySelector('#sheet-range-field').hidden=full;return}
  if(event.target.id==='sheet-discovery'&&state.paired&&state.auth?.owner){
    const epoch=assistantEpoch;privateSurfaceRevision++;
    try{await api('/api/assistant/sheets/discovery',{method:'PUT',body:JSON.stringify({enabled:event.target.checked})});if(epoch===assistantEpoch){clearSheetWork();await loadPrivateSurface(epoch);toast('Spreadsheet access updated. Listening stopped; enable Jarvis again when ready.')}}catch(error){if(epoch===assistantEpoch){event.target.checked=!event.target.checked;toast(error.message)}}return;
  }
  if(event.target.id!=='assistant-cloud'||!state.paired||!state.auth?.owner)return;
  privateSurfaceRevision++;
  const epoch=assistantEpoch;
  try{await api('/api/assistant/memory/cloud',{method:'PUT',body:JSON.stringify({enabled:event.target.checked})});if(epoch===assistantEpoch){await loadPrivateSurface(epoch);toast('Personal context updated. Listening stopped; enable Jarvis again when ready.')}}catch(error){if(epoch===assistantEpoch){event.target.checked=!event.target.checked;toast(error.message)}}
});
document.addEventListener('submit',async event=>{
  const form=event.target;
  if(!['memory-add','sheet-add','sheet-edit','sheet-search','sheet-browse'].includes(form.id)&&!form.matches('.memory-edit'))return;
  event.preventDefault();if(!state.paired||!state.auth?.owner)return;
  privateSurfaceRevision++;
  const epoch=assistantEpoch,button=form.querySelector('[type=submit]');if(button)button.disabled=true;
  try{
    if(form.id==='sheet-search')await findSheets(epoch);
    if(form.id==='sheet-browse')await readSheetCells(form.dataset.sheetId,epoch,sheetBrowseRange(form));
    if(form.id==='memory-add'||form.matches('.memory-edit')){
      const id=form.dataset.memoryId;
      await api('/api/assistant/memory'+(id?'/'+encodeURIComponent(id):''),{method:id?'PUT':'POST',body:JSON.stringify({text:form.elements.text.value})});
      if(epoch===assistantEpoch){if(!id)form.reset();await loadPrivateSurface(epoch);toast('Memory saved. Listening stopped to refresh context.')}
    }
    if(form.id==='sheet-add'){
      let id=form.elements.spreadsheetId.value.trim();
      if(id.startsWith('https://')){const url=new URL(id);if(url.origin!=='https://docs.google.com'||!/^\/spreadsheets\/d\/[A-Za-z0-9_-]+(?:\/|$)/.test(url.pathname))throw new Error('Choose a Google Sheets link.');id=url.pathname.split('/')[3]}
      await api('/api/assistant/sheets',{method:'POST',body:JSON.stringify({name:form.elements.name.value,spreadsheetId:id,access:form.elements.access.value,range:form.elements.access.value==='range'?form.elements.range.value:null})});
      if(epoch===assistantEpoch){form.reset();form.elements.range.disabled=true;form.elements.range.required=false;document.querySelector('#sheet-range-field').hidden=true;clearSheetWork();await loadPrivateSurface(epoch);toast('Spreadsheet access saved. Listening stopped to refresh context.')}
    }
    if(form.id==='sheet-edit'){
      const rows=[...form.querySelectorAll('.sheet-row')].map(row=>[...row.querySelectorAll('label')].map(label=>{const cell=label.querySelector('textarea'),original=JSON.parse(cell.dataset.original),type=label.querySelector('select').value;if(cell.value===String(original)&&type===typeof original)return null;if(type==='number'){const value=Number(cell.value);if(!cell.value.trim()||!Number.isFinite(value))throw new Error('Enter a valid number for each Number cell.');return value}if(type==='boolean'){if(!['true','false'].includes(cell.value))throw new Error('Enter true or false for each Yes/no cell.');return cell.value==='true'}return cell.value}));
      await api('/api/assistant/sheets/'+encodeURIComponent(form.dataset.sheetId)+'/propose',{method:'POST',body:JSON.stringify({values:rows,range:form.dataset.range})});
      if(epoch===assistantEpoch){await loadPrivateSurface(epoch);toast('Change prepared. Review the values below.')}
    }
  }catch(error){if(epoch===assistantEpoch)toast(error.message)}finally{if(button)button.disabled=false}
});
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-memory-delete],[data-memory-clear],[data-memory-export],[data-memory-history],[data-sheet-read],[data-sheet-delete],[data-sheet-explore],[data-sheet-tabs-more],[data-sheet-page],[data-sheet-search-more],[data-sheet-apply],[data-sheet-discard],[data-private-refresh]');
  if(!button||!state.paired||!state.auth?.owner)return;
  const epoch=assistantEpoch;
  if((button.hasAttribute('data-memory-clear')||button.hasAttribute('data-memory-history'))&&!button.dataset.confirm){button.dataset.confirm='true';button.textContent=button.hasAttribute('data-memory-clear')?'Confirm: forget all saved facts':'Confirm: clear conversation history';return}
  button.disabled=true;
  privateSurfaceRevision++;
  try{
    if(button.hasAttribute('data-memory-export')){
      const data=await api('/api/assistant/memory');if(epoch!==assistantEpoch)return;
      const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='Jarvis-memory.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Memory exported. Keep this personal file private.');return;
    }
    if(button.hasAttribute('data-memory-delete'))await api('/api/assistant/memory/'+encodeURIComponent(button.dataset.memoryDelete),{method:'DELETE'});
    if(button.hasAttribute('data-memory-clear'))await api('/api/assistant/memory',{method:'DELETE'});
    if(button.hasAttribute('data-memory-history'))await api('/api/voice/history',{method:'DELETE'});
    if(button.hasAttribute('data-sheet-delete')){await api('/api/assistant/sheets/'+encodeURIComponent(button.dataset.sheetDelete),{method:'DELETE'});if(epoch===assistantEpoch)clearSheetWork()}
    if(button.hasAttribute('data-sheet-search-more'))await findSheets(epoch,true);
    if(button.hasAttribute('data-sheet-explore'))await exploreSheet(button.dataset.sheetExplore,epoch);
    if(button.hasAttribute('data-sheet-tabs-more'))await exploreSheet(button.dataset.sheetTabsMore,epoch,Number(button.dataset.offset));
    if(button.hasAttribute('data-sheet-page')){const form=document.querySelector('#sheet-browse'),field=form.elements[button.dataset.sheetPage],step=field.name==='row'?100:10;field.value=Math.max(1,Math.min(Number(field.max),Number(field.value)+Number(button.dataset.direction)*step));await readSheetCells(form.dataset.sheetId,epoch,sheetBrowseRange(form))}
    if(button.hasAttribute('data-sheet-discard'))await api('/api/assistant/sheet-proposals/'+encodeURIComponent(button.dataset.sheetDiscard),{method:'DELETE'});
    if(button.hasAttribute('data-sheet-apply')){const result=await api('/api/assistant/sheet-proposals/'+encodeURIComponent(button.dataset.sheetApply)+'/apply',{method:'POST',signal:AbortSignal.timeout(25000)});if(epoch===assistantEpoch)toast(result.message)}
    if(button.hasAttribute('data-sheet-read')){
      await readSheetCells(button.dataset.sheetRead,epoch);
    }
    if(epoch===assistantEpoch){await loadPrivateSurface(epoch);if(button.hasAttribute('data-memory-delete')||button.hasAttribute('data-memory-clear'))toast('Memory forgotten. Listening stopped to refresh context.')}
  }catch(error){if(epoch===assistantEpoch)toast(error.message)}finally{if(button.isConnected&&epoch===assistantEpoch)button.disabled=false}
});

function sheetPreview(rows){return `<div class="sheet-values">${rows.map((row,r)=>`<div class="sheet-row">${row.map((cell,c)=>`<div class="sheet-preview"><small>Row ${r+1}, column ${c+1} · ${cell===null?'Unchanged':typeof cell==='string'?'Text':typeof cell==='boolean'?'Yes/no':'Number'}</small><span>${cell===null?'Leave as is':escapeHtml(String(cell))}</span></div>`).join('')}</div>`).join('')}</div>`}

function clearSheetWork(){privateSurfaceRevision++;for(const id of ['sheet-search-results','sheet-browser','sheet-result'])document.querySelector('#'+id)?.replaceChildren();const more=document.querySelector('[data-sheet-search-more]');if(more){more.hidden=true;delete more.dataset.token}}
async function findSheets(epoch,more=false){
  const form=document.querySelector('#sheet-search'),button=form.querySelector('[data-sheet-search-more]'),query=more?button.dataset.query:form.elements.query.value,revision=++privateSurfaceRevision;
  const result=await api('/api/assistant/sheets/search',{method:'POST',body:JSON.stringify({query,pageToken:more?button.dataset.token:null}),signal:AbortSignal.timeout(25000)});
  if(epoch!==assistantEpoch||revision!==privateSurfaceRevision)return;
  const target=document.querySelector('#sheet-search-results'),html=result.sheets.map(sheet=>`<div class="memory-edit"><h3>${escapeHtml(sheet.displayName||sheet.name)}</h3><p>${escapeHtml(sheet.spreadsheetId)} · ${sheet.canEdit?'Can edit':'Read only'}</p><button data-sheet-explore="${escapeHtml(sheet.id)}">Explore tabs</button></div>`).join('');
  if(more)target.insertAdjacentHTML('beforeend',html);else{document.querySelector('#sheet-browser').replaceChildren();document.querySelector('#sheet-result').replaceChildren();target.innerHTML=html||'<p>No matching spreadsheets on this page.</p>'}
  if(result.partial)target.insertAdjacentHTML('beforeend','<p>Google reported an incomplete search. Try a more specific name.</p>');
  button.hidden=!result.nextPageToken;button.dataset.token=result.nextPageToken||'';button.dataset.query=query;
}
async function exploreSheet(id,epoch,offset=0){
  const revision=++privateSurfaceRevision;document.querySelector('#sheet-result').replaceChildren();
  const result=await api('/api/assistant/sheets/'+encodeURIComponent(id)+'/tabs',{method:'POST',body:JSON.stringify({offset}),signal:AbortSignal.timeout(25000)});if(epoch!==assistantEpoch||revision!==privateSurfaceRevision)return;
  const tabs=result.tabs.filter(tab=>tab.supported),first=tabs[0];
  document.querySelector('#sheet-browser').innerHTML=`<h3>${escapeHtml(result.sheet.displayName||result.sheet.name)}</h3><p>All tabs are accessible. Browse up to 100 rows and 10 columns at a time. Sizes below describe the allocated grid, including blank cells.</p>${first?`<form id="sheet-browse" data-sheet-id="${escapeHtml(id)}" data-tabs="${escapeHtml(JSON.stringify(tabs))}"><label class="assistant-field">Tab<select name="tab">${tabs.map((tab,index)=>`<option value="${index}">${escapeHtml(tab.title)} · ${tab.rows} rows, ${tab.columns} columns</option>`).join('')}</select></label><label class="assistant-field">Start at row<input name="row" type="number" value="1" min="1" max="${first.rows}" required></label><label class="assistant-field">Start at column number<input name="column" type="number" value="1" min="1" max="${first.columns}" required></label><button type="submit">Read these cells</button><div class="page-actions"><button type="button" data-sheet-page="row" data-direction="-1">Earlier rows</button><button type="button" data-sheet-page="row" data-direction="1">Later rows</button><button type="button" data-sheet-page="column" data-direction="-1">Earlier columns</button><button type="button" data-sheet-page="column" data-direction="1">Later columns</button></div></form>`:'<p>No supported grid tabs on this page.</p>'}${result.tabs.some(tab=>!tab.supported)?'<p>Object and connected-data tabs are not supported by the cell editor.</p>':''}${offset?`<button data-sheet-tabs-more="${escapeHtml(id)}" data-offset="${Math.max(0,offset-50)}">Earlier tabs</button>`:''}${result.nextOffset!==null?`<button data-sheet-tabs-more="${escapeHtml(id)}" data-offset="${result.nextOffset}">More tabs</button>`:''}`;
}
function sheetColumn(number){let name='';while(number>0){number--;name=String.fromCharCode(65+number%26)+name;number=Math.floor(number/26)}return name}
function sheetBrowseRange(form){const tab=JSON.parse(form.dataset.tabs)[Number(form.elements.tab.value)],row=Number(form.elements.row.value),column=Number(form.elements.column.value);if(!Number.isInteger(row)||!Number.isInteger(column)||row<1||column<1||row>tab.rows||column>tab.columns)throw new Error('Choose a starting cell within the tab.');return "'"+tab.title.replaceAll("'","''")+"'!"+sheetColumn(column)+row+':'+sheetColumn(Math.min(tab.columns,column+9))+Math.min(tab.rows,row+99)}
async function readSheetCells(id,epoch,range=null){
  const revision=++privateSurfaceRevision;document.querySelector('#sheet-result').replaceChildren();
  const result=await api('/api/assistant/sheets/'+encodeURIComponent(id)+'/read',{method:'POST',body:JSON.stringify({range}),signal:AbortSignal.timeout(25000)});if(epoch!==assistantEpoch||revision!==privateSurfaceRevision)return;
  const rows=result.values.length?result.values:[['']];
  document.querySelector('#sheet-result').innerHTML=`<form id="sheet-edit" data-sheet-id="${escapeHtml(result.sheet.id)}" data-range="${escapeHtml(result.sheet.range)}"><h3>${escapeHtml(result.sheet.displayName||result.sheet.name)}</h3><p>${escapeHtml(result.sheet.range)}</p><div class="sheet-values">${rows.map((row,r)=>`<div class="sheet-row">${(row.length?row:['']).map((cell,c)=>`<label>Row offset ${r+1}, column offset ${c+1}<textarea rows="2" maxlength="500" data-original="${escapeHtml(JSON.stringify(cell))}">${escapeHtml(String(cell))}</textarea><select aria-label="Cell value type">${['string','number','boolean'].map(type=>`<option value="${type}" ${typeof cell===type?'selected':''}>${type==='string'?'Text':type==='number'?'Number':'Yes/no'}</option>`).join('')}</select></label>`).join('')}</div>`).join('')}</div><p class="section-note">Edit individual cells in this range. Unchanged cells are preserved. Preparing a change does not write it.</p><button type="submit" ${result.sheet.canEdit===false?'disabled':''}>Preview change</button></form>`;
}
