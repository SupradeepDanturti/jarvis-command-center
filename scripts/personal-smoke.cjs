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
  let cloud=false,facts=[{id:'suggested',text:'I like jazz',pending:1,source:'agent',updated:1}],sheets=[],proposals=[],written=0,previewRows;
  await page.route('**/api/assistant/**',async route=>{
   const req=route.request(),endpoint=new URL(req.url()).pathname.slice('/api/assistant/'.length),method=req.method();let body={ok:true};
   if(endpoint==='status')body={enabled:true,clientConfigured:true,account:{email:'qa@example.test'},calendarReady:true,sheetsReady:true,cloudContext:cloud};
   else if(endpoint==='memory/cloud')cloud=req.postDataJSON().enabled;
   else if(endpoint==='memory'&&method==='GET')body={facts,cloudContext:cloud,profile:{address:'sir'},recentConversation:[],lastContext:null,limits:{facts:200}};
   else if(endpoint==='memory'&&method==='POST')facts.push({id:'saved',text:req.postDataJSON().text,pending:0,source:'owner',updated:1});
   else if(endpoint==='memory'&&method==='DELETE')facts=[];
   else if(endpoint.startsWith('memory/')){const id=endpoint.split('/')[1];if(method==='DELETE')facts=facts.filter(fact=>fact.id!==id);else facts=facts.map(fact=>fact.id===id?{...fact,text:req.postDataJSON().text,pending:0}:fact)}
   else if(endpoint==='sheets'&&method==='GET')body={sheets,proposals};
   else if(endpoint==='sheets'&&method==='POST'){sheets.push({id:'tracker',...req.postDataJSON()})}
   else if(endpoint==='sheets/tracker/read')body={ok:true,sheet:sheets[0],values:[['<img src=x onerror=alert(1)>','line1\nline2\ttext'],['original',3]]};
   else if(endpoint==='sheets/tracker/propose'){previewRows=req.postDataJSON().values;proposals=[{id:'preview',sheet:sheets[0],values:previewRows,expiresAt:Date.now()/1000+300}]}
   else if(endpoint==='sheet-proposals/preview/apply'){written++;proposals=[];body={ok:true,message:'Sheet values updated.'}}
   else if(endpoint==='sheet-proposals/preview'&&method==='DELETE')proposals=[];
   else if(endpoint==='sheets/tracker'&&method==='DELETE')sheets=[];
   else throw Error('Unexpected personal endpoint '+endpoint);
   await route.fulfill({json:body});
  });
  async function screen(id){await page.evaluate(id=>goPage(id),id);await page.waitForTimeout(150)}
  await screen('memory');await page.locator('#assistant-cloud').check();await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Personal context updated'));
  await page.locator('#memory-add textarea').fill('<script>owner fact</script>');await page.locator('#memory-add button').click();await page.waitForFunction(()=>document.querySelectorAll('#memory-list form').length===2);
  assert.equal(await page.locator('#memory-list script').count(),0);
  await page.locator('[data-memory-id=suggested] textarea').fill('I prefer jazz');await page.locator('[data-memory-id=suggested] [type=submit]').click();await page.waitForFunction(()=>document.querySelector('[data-memory-id=suggested] [type=submit]').textContent==='Save changes');
  await page.locator('[data-memory-delete=saved]').click();await page.waitForFunction(()=>document.querySelectorAll('#memory-list form').length===1);
  await screen('sheets');await page.locator('#sheet-add [name=name]').fill('Tracker');await page.locator('#sheet-add [name=spreadsheetId]').fill('https://docs.google.com/spreadsheets/d/fixture_sheet_123/edit');await page.locator('#sheet-add [name=range]').fill('Sheet1!A1:C4');await page.locator('#sheet-add button').click();await page.locator('[data-sheet-read]').waitFor();assert.equal(sheets[0].spreadsheetId,'fixture_sheet_123');
  await page.locator('[data-sheet-read]').click();await page.locator('#sheet-edit').waitFor();assert.equal(await page.locator('#sheet-result img').count(),0);
  await page.locator('#sheet-edit textarea').first().fill('replacement');await page.locator('#sheet-edit textarea').nth(1).fill('line1\nline2\ttext\nnew');await page.locator('#sheet-edit textarea').last().fill('4');await page.locator('#sheet-edit [type=submit]').click();await page.locator('[data-sheet-apply]').waitFor();assert.equal(written,0);assert.equal(previewRows[0][1],'line1\nline2\ttext\nnew');assert.equal(previewRows[1][0],null);assert.equal(previewRows[1][1],4);
  assert.match(await page.locator('#sheet-proposals').innerText(),/replacement/);await page.locator('[data-sheet-apply]').click();await page.waitForFunction(()=>document.querySelector('#sheet-proposals').textContent.includes('No pending'));assert.equal(written,1);
  for(const [width,height,label] of [[1280,800,'landscape'],[800,1280,'portrait'],[390,844,'narrow']]){
   await page.setViewportSize({width,height});for(const id of ['memory','sheets']){await screen(id);assert.equal(await page.locator('#page-content').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);assert.equal(await page.locator('.surface-dock').isVisible(),true);await page.screenshot({path:path.join(root,'artifacts',`personal-${id}-${label}.png`),fullPage:true})}
  }
  assert.equal(await page.evaluate(()=>Object.values(localStorage).some(value=>/I prefer jazz|owner fact|fixture_sheet/.test(value))),false);
  await screen('memory');await page.locator('[data-memory-clear]').click();assert.equal(facts.length,1);await page.locator('[data-memory-clear]').click();await page.waitForFunction(()=>document.querySelector('#memory-list').textContent.includes('No saved'));assert.equal(facts.length,0);
  await page.evaluate(()=>showPairing());assert.equal(await page.locator('#assistant-private').innerText(),'');assert.deepEqual(errors,[]);
  console.log('Personal tools smoke passed: memory CRUD/review/consent, registered Sheets, safe multiline previews, explicit apply, no local storage and three layouts.');
 }finally{if(page)try{await page.evaluate(async()=>{await fetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'}})})}catch{}if(context)await context.close();await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
