// Fresh trusted QA browser; personal operations are fixtures, never the owner's account or memory.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),browser=await chromium.launch({channel:'msedge',headless:true});let context,page;
 try{
  context=await browser.newContext({viewport:{width:1280,height:800}});page=await context.newPage();const errors=[];
  page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error'&&/Content Security Policy|Refused/i.test(message.text()))errors.push(message.text())});
  await page.goto('https://localhost:18761');await page.waitForFunction(()=>state.auth?.local);
  await page.locator('#device-name').fill('Personal tools QA');await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());await page.locator('#pair-form button').click();await page.waitForFunction(()=>state.paired&&state.auth?.owner&&state.socket?.readyState===WebSocket.OPEN);
  let cloud=false,discovery=false,facts=[{id:'suggested',text:'I like jazz',pending:1,source:'agent',updated:1}],sheets=[],proposals=[],written=0,previewRows,lastRange,searchPage;
  const found={id:'found',name:'Planner <img src=x>',spreadsheetId:'fixture_sheet_789',access:'spreadsheet',range:null,canEdit:true};
  await page.route('**/api/assistant/**',async route=>{
   const req=route.request(),endpoint=new URL(req.url()).pathname.slice('/api/assistant/'.length),method=req.method();let body={ok:true};
   if(endpoint==='status')body={enabled:true,clientConfigured:true,account:{email:'qa@example.test'},calendarReady:true,sheetsReady:true,sheetSearchReady:true,cloudContext:cloud};
   else if(endpoint==='profile')body={address:'sir',timezone:'America/Toronto',tone:'jarvis'};
   else if(endpoint==='memory/cloud')cloud=req.postDataJSON().enabled;
   else if(endpoint==='memory'&&method==='GET')body={facts,cloudContext:cloud,profile:{address:'sir'},recentConversation:[],lastContext:null,limits:{facts:200}};
   else if(endpoint==='memory/files'&&method==='GET')body={enabled:true,files:[]};
   else if(endpoint==='memory'&&method==='POST')facts.push({id:'saved',text:req.postDataJSON().text,pending:0,source:'owner',updated:1});
   else if(endpoint==='memory'&&method==='DELETE')facts=[];
   else if(endpoint.startsWith('memory/')){const id=endpoint.split('/')[1];if(method==='DELETE')facts=facts.filter(fact=>fact.id!==id);else facts=facts.map(fact=>fact.id===id?{...fact,text:req.postDataJSON().text,pending:0}:fact)}
   else if(endpoint==='sheets'&&method==='GET')body={sheets,proposals,discoveryEnabled:discovery,discoveryReady:true};
   else if(endpoint==='sheets/discovery'){discovery=req.postDataJSON().enabled}
   else if(endpoint==='sheets/search'){searchPage=req.postDataJSON().pageToken;body={ok:true,sheets:searchPage?[]:[found],nextPageToken:searchPage?null:'next-fixture',partial:false}}
   else if(endpoint==='sheets'&&method==='POST'){sheets.push({id:sheets.length?'whole':'tracker',...req.postDataJSON()})}
   else if(/^sheets\/(tracker|whole|found)\/tabs$/.test(endpoint)){body={ok:true,sheet:[...sheets,found].find(sheet=>sheet.id===endpoint.split('/')[1]),tabs:req.postDataJSON().offset?[{title:'Later tab',rows:100,columns:10,supported:true}]:[{title:"Owner's tab <img>",rows:250,columns:30,supported:true},{title:'Second tab',rows:25,columns:5,supported:true}],nextOffset:req.postDataJSON().offset?null:50}}
   else if(/^sheets\/(tracker|whole|found)\/read$/.test(endpoint)){const sheet=[...sheets,found].find(sheet=>sheet.id===endpoint.split('/')[1]);lastRange=req.postDataJSON().range||sheet.range;body={ok:true,sheet:{...sheet,range:lastRange},values:[['<img src=x onerror=alert(1)>','line1\nline2\ttext'],['original',3]]}}
   else if(/^sheets\/(tracker|whole|found)\/propose$/.test(endpoint)){previewRows=req.postDataJSON().values;const sheet=[...sheets,found].find(sheet=>sheet.id===endpoint.split('/')[1]);proposals=[{id:'preview',sheet:{...sheet,range:req.postDataJSON().range||sheet.range},values:previewRows,expiresAt:Date.now()/1000+300}]}
   else if(endpoint==='sheet-proposals/preview/apply'){written++;proposals=[];body={ok:true,message:'Sheet values updated.'}}
   else if(endpoint==='sheet-proposals/preview'&&method==='DELETE')proposals=[];
   else if(endpoint==='sheets/tracker'&&method==='DELETE')sheets=[];
   else throw Error('Unexpected personal endpoint '+endpoint);
   await route.fulfill({json:body});
  });
  async function screen(id){await page.evaluate(id=>goPage(id),id);await page.waitForTimeout(150)}
  await page.locator('#more-toggle').click();
  for(const id of ['agenda','connections','sheets','memory'])assert.equal(await page.locator(`#more-menu [data-page="${id}"]`).count(),0);
  await page.locator('#more-menu [data-page=personalization]').click();await page.waitForFunction(()=>document.querySelector('#assistant-profile [type=submit]')?.disabled===false);
  assert.equal(await page.locator('.assistant-links [data-go=personalization]').getAttribute('aria-current'),'page');
  for(const id of ['agenda','connections','sheets','memory'])assert.equal(await page.locator(`.assistant-links [data-go="${id}"]`).count(),1);
  await page.locator('.assistant-links [data-go=memory]').click();await page.locator('#memory-add').waitFor({state:'attached'});assert.equal(await page.locator('#more-menu [data-page=personalization]').getAttribute('aria-current'),'page');
  await page.reload();await page.waitForFunction(()=>state.paired&&state.socket?.readyState===WebSocket.OPEN&&document.querySelector('#assistant-cloud')?.disabled===false);
  assert.equal(await page.locator('.assistant-links [data-go=memory]').getAttribute('aria-current'),'page');
  await page.goBack();await page.waitForFunction(()=>state.page==='personalization'&&document.querySelector('#assistant-profile [type=submit]')?.disabled===false);
  await screen('memory');await page.locator('details').filter({has:page.locator('#memory-add')}).locator('summary').first().click();await page.locator('#assistant-cloud').check();await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Personal context updated'));
  await page.locator('#memory-add textarea').fill('<script>owner fact</script>');await page.locator('#memory-add button').click();await page.waitForFunction(()=>document.querySelectorAll('#memory-list form').length===2);
  assert.equal(await page.locator('#memory-list script').count(),0);
  await page.locator('[data-memory-id=suggested] textarea').fill('I prefer jazz');await page.locator('[data-memory-id=suggested] [type=submit]').click();await page.waitForFunction(()=>document.querySelector('[data-memory-id=suggested] [type=submit]').textContent==='Save changes');
  await page.locator('[data-memory-delete=saved]').click();await page.waitForFunction(()=>document.querySelectorAll('#memory-list form').length===1);
  await screen('sheets');await page.locator('summary').filter({hasText:'Or give access'}).click();await page.locator('#sheet-add [name=name]').fill('Tracker');await page.locator('#sheet-add [name=spreadsheetId]').fill('https://docs.google.com/spreadsheets/d/fixture_sheet_123/edit');await page.locator('#sheet-add [name=access]').selectOption('range');await page.locator('#sheet-add [name=range]').fill('Sheet1!A1:C4');await page.locator('#sheet-add button').click();await page.locator('[data-sheet-read]').waitFor();assert.equal(sheets[0].spreadsheetId,'fixture_sheet_123');
  await page.locator('[data-sheet-read]').click();await page.locator('#sheet-edit').waitFor();assert.equal(await page.locator('#sheet-result img').count(),0);
  await page.locator('#sheet-edit textarea').first().fill('replacement');await page.locator('#sheet-edit textarea').nth(1).fill('line1\nline2\ttext\nnew');await page.locator('#sheet-edit textarea').last().fill('4');await page.locator('#sheet-edit [type=submit]').click();await page.locator('[data-sheet-apply]').waitFor();assert.equal(written,0);assert.equal(previewRows[0][1],'line1\nline2\ttext\nnew');assert.equal(previewRows[1][0],null);assert.equal(previewRows[1][1],4);
  assert.match(await page.locator('#sheet-proposals').innerText(),/replacement/);await page.locator('[data-sheet-apply]').click();await page.waitForFunction(()=>document.querySelector('#sheet-proposals').textContent.includes('No pending'));assert.equal(written,1);
  await page.locator('#sheet-add [name=name]').fill('Whole file');await page.locator('#sheet-add [name=spreadsheetId]').fill('fixture_sheet_456');assert.equal(await page.locator('#sheet-add [name=access]').inputValue(),'spreadsheet');assert.equal(await page.locator('#sheet-range-field').isVisible(),false);await page.locator('#sheet-add button').click();await page.locator('[data-sheet-explore=whole]').waitFor();assert.equal(sheets[1].range,null);
  await page.locator('[data-sheet-explore=whole]').click();await page.locator('#sheet-browse').waitFor();await page.locator('#sheet-browse [type=submit]').click();await page.locator('#sheet-edit').waitFor();assert.equal(lastRange,"'Owner''s tab <img>'!A1:J100");assert.equal(await page.locator('#sheet-browser img').count(),0);
  await page.locator('[data-sheet-page=row][data-direction="1"]').click();await page.waitForFunction(()=>document.querySelector('#sheet-edit')?.dataset.range.endsWith('A101:J200'));
  await page.locator('[data-sheet-page=column][data-direction="1"]').click();await page.waitForFunction(()=>document.querySelector('#sheet-edit')?.dataset.range.endsWith('K101:T200'));
  await page.locator('#sheet-browse [name=tab]').selectOption('1');await page.locator('#sheet-browse [type=submit]').click();await page.waitForFunction(()=>document.querySelector('#sheet-edit')?.dataset.range==="'Second tab'!A1:E25");
  await page.locator('[data-sheet-tabs-more][data-offset="50"]').click();await page.waitForFunction(()=>document.querySelector('#sheet-browse [name=tab]').textContent.includes('Later tab'));
  await page.locator('#sheet-discovery').check();await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Spreadsheet access updated'));
  await page.locator('#sheet-search [name=query]').fill('Planner');await page.locator('#sheet-search [type=submit]').click();await page.locator('[data-sheet-explore=found]').waitFor();assert.equal(await page.locator('#sheet-search-results img').count(),0);await page.locator('[data-sheet-search-more]').click();await page.waitForFunction(()=>document.querySelector('[data-sheet-search-more]').hidden);assert.equal(searchPage,'next-fixture');
  await page.locator('[data-sheet-explore=found]').click();await page.locator('#sheet-browse [type=submit]').click();await page.locator('#sheet-edit').waitFor();await page.locator('#sheet-edit textarea').first().fill('discovered change');await page.locator('#sheet-edit [type=submit]').click();await page.locator('[data-sheet-apply]').waitFor();assert.equal(proposals[0].sheet.range,"'Owner''s tab <img>'!A1:J100");assert.equal(written,1);
  for(const [width,height,label] of [[1280,800,'landscape'],[800,1280,'portrait'],[390,844,'narrow']]){
   await page.setViewportSize({width,height});for(const id of ['memory','sheets']){await screen(id);assert.equal(await page.locator('#page-content').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);assert.equal(await page.locator('.surface-dock').isVisible(),true);await page.screenshot({path:path.join(root,'artifacts',`personal-${id}-${label}.png`),fullPage:true})}
  }
  assert.equal(await page.evaluate(()=>Object.values(localStorage).some(value=>/I prefer jazz|owner fact|fixture_sheet/.test(value))),false);
  await screen('memory');await page.locator('details').filter({has:page.locator('#memory-add')}).locator('summary').first().click();await page.locator('[data-memory-clear]').click();assert.equal(facts.length,1);await page.locator('[data-memory-clear]').click();await page.waitForFunction(()=>document.querySelector('#memory-list').textContent.includes('No saved'));assert.equal(facts.length,0);
  await page.evaluate(()=>showPairing());assert.equal(await page.locator('#assistant-private').innerText(),'');assert.deepEqual(errors,[]);
  console.log('Personal tools smoke passed: grouped Personalization menu, child navigation/reload/back, memory, full Sheets/discovery, exact previews, explicit apply, no local storage and three layouts.');
 }finally{if(page)try{await page.evaluate(async()=>{await fetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'}})})}catch{}if(context)await context.close();await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
