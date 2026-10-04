// UI checks mock all voice mutations: no API key, microphone, or sound is touched.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1280,height:800}}),page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const current={phase:'off',message:'Microphone off.',busy:false,enabled:false,keyConfigured:false,modelsInstalled:true,dependenciesInstalled:true,ready:false,lastHeard:'',lastReply:'',inputId:'webcam',followupSeconds:15,history:[]};
  const history=[{id:1,created:Date.now()/1000,heard:'Open that app.',reply:'Which app would you like, sir?',action:null,sources:[]},{id:2,created:Date.now()/1000,heard:'Steam.',reply:'Opening Steam, sir.',action:{name:'launch_app',arguments:{id:'steam'},ok:true,message:'Opening Steam'},sources:[]},{id:3,created:Date.now()/1000,heard:'Search NASA.',reply:'Here is the update, sir.',action:null,sources:[{url:'https://www.nasa.gov/example',title:'NASA <script>source</script>'},{url:'javascript:alert(1)',title:'Bad source'}]}];
  current.history=history;
  const sent=[];
  try{
    await page.route('**/api/voice/**',async route=>{
      const request=route.request(),endpoint=request.url().split('/').pop().split('?')[0];
      if(request.headers()['x-g16-qa-native']==='1'){assert.equal(request.method(),'GET');return route.continue()}
      if(endpoint==='status')return route.fulfill({json:current});
      if(endpoint==='history'&&request.method()==='GET')return route.fulfill({json:history});
      if(endpoint==='history'&&request.method()==='DELETE'){history.length=0;current.history=[];return route.fulfill({json:{ok:true}})}
      if(endpoint==='followup'){current.followupSeconds=request.postDataJSON().seconds;return route.fulfill({json:current})}
      if(endpoint==='inputs')return route.fulfill({json:[{id:'webcam',name:'Webcam microphone'},{id:'headset',name:'Headset microphone'}]});
      sent.push({endpoint,method:request.method()});
      if(endpoint==='input'){current.inputId=request.postDataJSON().id;return route.fulfill({json:current})}
      if(endpoint==='key'){current.keyConfigured=request.method()!=='DELETE';current.ready=current.keyConfigured;return route.fulfill({json:{ok:true,keyConfigured:current.keyConfigured}})}
      if(endpoint==='enabled'){current.enabled=request.postDataJSON().enabled;current.busy=current.enabled;current.phase=current.enabled?'listening':'off';return route.fulfill({json:current})}
      if(endpoint==='preview')return route.fulfill({json:current});
      throw new Error('Unexpected voice endpoint');
    });
    await page.goto('https://localhost:18761/#voice');
    await page.waitForFunction(()=>state.auth?.local===true);
    await page.locator('#device-name').fill('Jarvis UI QA');
    await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());
    await page.locator('#pair-form button').click();
    await page.waitForFunction(()=>state.paired&&document.querySelector('#voice-phase')?.textContent==='Standing by.');
    // Use Edge's real Windows trust store; the Node API context has a separate CA store.
    const readNative=endpoint=>page.evaluate(async endpoint=>{const r=await fetch(`/api/voice/${endpoint}`,{headers:{'X-G16-QA-Native':'1'}});return {status:r.status,body:await r.json()}},endpoint);
    const nativeStatus=await readNative('status');
    assert.equal(nativeStatus.status,200);
    const native=nativeStatus.body;
    assert.equal(typeof native.keyConfigured,'boolean');
    assert.equal(Object.hasOwn(native,'key'),false);
    const nativeInputs=await readNative('inputs');
    assert.equal(nativeInputs.status,200);
    const devices=nativeInputs.body;
    assert.equal(devices.length>0,true,'Native fresh-process microphone enumeration returns actual inputs');
    if(native.inputId)assert.equal(devices.some(d=>d.id===native.inputId),true,'Saved microphone resolves to a current input');
    assert.equal(devices.some(d=>/Stereo Mix/i.test(d.name)),false);
    await page.waitForFunction(()=>document.querySelectorAll('.voice-history-turn').length===3);
    assert.match(await page.locator('#voice-history-list').innerText(),/launch_app.*steam/);
    assert.equal(await page.locator('.voice-source').count(),1);
    assert.equal(await page.locator('.voice-source').getAttribute('href'),'https://www.nasa.gov/example');
    assert.equal(await page.locator('#voice-history-list script').count(),0);
    await page.locator('#voice-followup').selectOption('30');
    await page.waitForFunction(()=>voiceState.followupSeconds===30);
    assert.equal(await page.locator('#voice-api-key').getAttribute('type'),'password');
    await page.waitForFunction(()=>document.querySelector('#voice-input').value==='webcam');
    assert.equal(await page.locator('#voice-toggle').isDisabled(),true,'No key means no microphone start');
    assert.equal(await page.locator('#voice-preview').isEnabled(),true,'Local preview does not require OpenAI');
    await page.locator('#voice-api-key').fill('sk-qa-only-never-sent-to-server');
    await page.locator('#voice-key-form button').click();
    await page.waitForFunction(()=>document.querySelector('#voice-api-key').value===''&&!document.querySelector('#voice-toggle').disabled);
    assert.equal(await page.evaluate(()=>Object.values(localStorage).some(v=>v.includes('sk-qa-only'))),false);
    await page.locator('#voice-input').selectOption('headset');
    await page.waitForFunction(()=>voiceState.inputId==='headset');
    await page.locator('[data-voice-refresh]').click();
    await page.waitForFunction(()=>document.querySelector('#voice-input')?.value==='headset');
    await page.locator('#voice-toggle').click();
    await page.waitForFunction(()=>document.querySelector('#voice-toggle').textContent==='Turn off Jarvis');
    assert.equal(await page.locator('#voice-input').isDisabled(),true);
    assert.equal(await page.locator('#voice-followup').isDisabled(),true);
    current.phase='followup';current.message='Your turn · listening for your reply.';
    await page.waitForFunction(()=>document.querySelector('#voice-phase').textContent==='Your turn.');
    assert.equal(await page.locator('#voice-preview').isDisabled(),true);
    await page.locator('#voice-toggle').click();
    await page.waitForFunction(()=>document.querySelector('#voice-toggle').textContent==='Turn on Jarvis');
    fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
    await page.screenshot({path:path.join(root,'artifacts/jarvis-landscape.png'),fullPage:true});
    assert.equal(await page.locator('#voice-key-details').getAttribute('open'),null);
    assert.equal(await page.evaluate(()=>{const setup=document.querySelector('.voice-setup').getBoundingClientRect(),dock=document.querySelector('.surface-dock').getBoundingClientRect();return setup.bottom<dock.top}),true,'Configured voice controls stay above the dock');
    assert.equal(await page.evaluate(()=>document.querySelector('#page-content').scrollWidth<=document.querySelector('#page-content').clientWidth),true);
    await page.locator('#more-toggle').click();await page.locator('[data-page="system"]').click();
    await page.waitForFunction(()=>document.querySelector('#voice-input')?.value==='headset');
    await page.locator('#voice-input').selectOption('webcam');
    await page.waitForFunction(()=>voiceState.inputId==='webcam');
    await page.locator('[data-go="voice"]').click();
    await page.waitForFunction(()=>document.querySelector('#voice-input')?.value==='webcam');
    await page.locator('#voice-key-details summary').click();
    await page.locator('#voice-delete-key').click();
    await page.waitForFunction(()=>document.querySelector('#voice-toggle').disabled);
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('#voice-history-clear').click();
    await page.waitForFunction(()=>document.querySelectorAll('.voice-history-turn').length===0);
    assert.equal(sent.filter(x=>x.endpoint==='input').length,2);
    assert.deepEqual(errors,[]);
    console.log('Jarvis browser checks passed: setup, private key field, microphone dropdowns, toggle and navigation. All voice writes mocked. History, safe inline citations, follow-up settings and clear-history checked.');
  }finally{
    await page.evaluate(async()=>{if(state.paired)await fetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'}})}).catch(()=>{});
    await context.close();await browser.close();
  }
})().catch(error=>{console.error(String(error.message).split('\n')[0]);process.exitCode=1});
