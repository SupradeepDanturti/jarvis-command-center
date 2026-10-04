// UI checks mock all voice mutations: no API key, microphone, or sound is touched.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1280,height:800}}),page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{window.qaCsp=[];document.addEventListener('securitypolicyviolation',e=>qaCsp.push(e.violatedDirective))});
  // Isolate this UI check from the owner's shared Rest screen without waking monitors.
  const idleRest={instance:'f'.repeat(24),revision:0,serverTime:Date.now(),rest:false,displayAvailable:true,keepingAwake:false,alarm:null,message:'',audio:{ready:false,phase:'off',message:''}};
  await page.route('**/api/alarms',route=>{
    assert.equal(route.request().method(),'GET');return route.fulfill({json:idleRest});
  });
  await page.addInitScript(data=>{
    const Native=window.WebSocket;
    window.WebSocket=class extends Native{
      set onmessage(receive){super.onmessage=event=>{const packet=JSON.parse(event.data);packet.rest={...data,serverTime:packet.serverTime};receive({data:JSON.stringify(packet)})}}
    };
  },idleRest);
  const current={phase:'off',message:'Microphone off.',busy:false,enabled:false,keyConfigured:false,modelsInstalled:true,dependenciesInstalled:true,ready:false,lastHeard:'',lastReply:'',inputId:'webcam',outputId:null,alertsEnabled:true,followupSeconds:15,history:[]};
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
      if(endpoint==='outputs')return route.fulfill({json:[{id:'laptop-speaker',name:'Speakers (Realtek Audio)'}]});
      if(endpoint==='output'){current.outputId=request.postDataJSON().id;return route.fulfill({json:current})}
      if(endpoint==='alerts'){current.alertsEnabled=request.postDataJSON().enabled;return route.fulfill({json:current})}
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
    await page.waitForFunction(()=>state.paired&&document.querySelector('#voice-phase')?.textContent==='Standing by, sir.');
    // Use Edge's real Windows trust store; the Node API context has a separate CA store.
    const readNative=endpoint=>page.evaluate(async endpoint=>{const r=await fetch(`/api/voice/${endpoint}`,{headers:{'X-G16-QA-Native':'1'}});return {status:r.status,body:await r.json()}},endpoint);
    const nativeStatus=await readNative('status');
    assert.equal(nativeStatus.status,200);
    const native=nativeStatus.body;
    assert.equal(native.wakePhrase,'Jarvis');
    assert.match(await page.locator('.voice-intro').innerText(),/Say “Jarvis”, pause, then ask/);
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
    await page.waitForFunction(()=>document.querySelector('#voice-phase').textContent==='Your turn, sir.');
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
    await page.locator('#voice-output').selectOption('laptop-speaker');
    await page.waitForFunction(()=>voiceState.outputId==='laptop-speaker');
    await page.locator('#voice-alert-toggle').click();
    await page.waitForFunction(()=>voiceState.alertsEnabled===false);
    await page.locator('#voice-alert-toggle').click();
    await page.waitForFunction(()=>voiceState.alertsEnabled===true);
    assert.equal(await page.locator('.jarvis-identity .jarvis-mask').count(),1);
    assert.equal(await page.locator('.jarvis-identity .jarvis-mask').getAttribute('src'),'/static/assets/iron-man-helmet.png');
    await page.waitForFunction(()=>document.querySelector('.jarvis-mask')?.naturalWidth===393);
    await page.route('**/api/media/**',route=>route.request().method()==='POST'?route.fulfill({json:{ok:true}}):route.continue());
    current.enabled=true;current.busy=true;current.phase='listening';
    await page.locator('[data-page="home"]').click();
    await page.waitForFunction(()=>document.querySelector('#jarvis-home')?.dataset.active==='false'&&!document.querySelector('#jarvis-home').hidden);
    for(const phase of ['recording','transcribing','thinking','speaking','followup','alert']){
      current.phase=phase;current.message=phase==='thinking'?'Working on your request.':'Voice activity.';current.lastReply='At your service, sir. Your laptop is within reach.';
      await page.waitForFunction(phase=>document.querySelector('#jarvis-home')?.dataset.phase===phase,phase);
      assert.equal(await page.locator('#jarvis-home').isVisible(),true);
      assert.equal(await page.locator('#surface-background').getAttribute('data-scene'),'blackhole');
      assert.equal(await page.locator('#jarvis-home').evaluate(el=>getComputedStyle(el).pointerEvents),'none');
    }
    for(const [width,height] of [[1280,800],[1280,720],[1024,600],[960,600],[412,915],[640,400]]){
      await page.setViewportSize({width,height});
      current.phase='speaking';
      await page.waitForFunction(()=>document.querySelector('#jarvis-home')?.dataset.phase==='speaking');
      const layout=await page.evaluate(()=>{
        const hud=document.querySelector('.jarvis-home-active').getBoundingClientRect(),telemetry=document.querySelector('.orbit-telemetry').getBoundingClientRect(),dock=document.querySelector('.surface-dock').getBoundingClientRect();
        const button=document.querySelector('[data-media="volume-up"]'),r=button.getBoundingClientRect();
        const elements=[...document.querySelectorAll('.jarvis-home-center,.jarvis-home-copy h3,.jarvis-core,.jarvis-readings')].filter(el=>getComputedStyle(el).display!=='none');const contentsFit=elements.every(el=>{const r=el.getBoundingClientRect();return r.top>=hud.top-2&&r.bottom<=hud.bottom+2});
        return {fit:contentsFit&&hud.left>=0&&hud.right<=innerWidth+1&&hud.bottom<=telemetry.top+1&&hud.bottom<dock.top,tappable:button.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))};
      });
      assert.equal(layout.fit,true,`Home HUD fits ${width}×${height}`);
      if(width>=960)assert.equal(layout.tappable,true,'HUD does not capture sound-control taps');
    }
    await page.setViewportSize({width:1280,height:800});
    await page.screenshot({path:path.join(root,'artifacts/jarvis-home-speaking.png'),fullPage:true});
    // The same HUD stays live throughout all screens, including immersive artwork.
    for(const widthHeight of [[1280,800],[412,915],[640,400]]){
      await page.setViewportSize({width:widthHeight[0],height:widthHeight[1]});
      for(const id of ['gaming','games','apps','hardware','graphs','system','devices','voice','clock','ambient','rest']){
        await page.evaluate(id=>goPage(id),id);
        current.phase='thinking';
        await page.waitForFunction(()=>document.querySelector('#jarvis-home')?.dataset.phase==='thinking'&&!document.querySelector('#jarvis-home').hidden);
        current.phase='speaking';
        await page.waitForFunction(()=>document.querySelector('#jarvis-home')?.dataset.phase==='speaking');
        const layout=await page.locator('#jarvis-home').evaluate(el=>{
          const r=el.getBoundingClientRect(),dock=document.querySelector('.surface-dock').getBoundingClientRect();
          return {single:document.querySelectorAll('#jarvis-home').length===1,fit:r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<dock.top,pointer:getComputedStyle(el).pointerEvents};
        });
        assert.equal(layout.single,true);assert.equal(layout.fit,true,`${id} HUD fits ${widthHeight}`);assert.equal(layout.pointer,'none');
        if(id==='clock'||id==='ambient'){
          await page.evaluate(()=>setPresentation(true));
          assert.equal(await page.locator('#jarvis-home').isVisible(),true,'HUD remains available in immersive scenes');
          await page.evaluate(()=>setPresentation(false));
        }
      }
    }
    await page.setViewportSize({width:1280,height:800});
    await page.evaluate(()=>goPage('clock'));
    await page.screenshot({path:path.join(root,'artifacts/jarvis-clock-speaking.png'),fullPage:true});
    await page.evaluate(()=>goPage('home'));

    await page.locator('[data-media="volume-up"]').click();
    assert.equal(await page.evaluate(()=>{const wasStale=state.stale;state.stale=true;paintJarvisHome();const hidden=document.querySelector('#jarvis-home').hidden;state.stale=wasStale;paintJarvisHome();return hidden}),true,'Disconnected HUD cannot show old activity');
    await page.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await page.locator('.jarvis-ring-outer').evaluate(el=>getComputedStyle(el).animationName),'none');
    await page.emulateMedia({reducedMotion:'no-preference'});
    current.busy=false;current.enabled=false;current.phase='off';
    await page.waitForFunction(()=>document.querySelector('#jarvis-home').hidden);
    await page.locator('#more-toggle').click();await page.locator('[data-page="voice"]').click();
    await page.waitForFunction(()=>document.querySelector('#voice-output')?.value==='laptop-speaker');
    await page.screenshot({path:path.join(root,'artifacts/jarvis-landscape.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.querySelector('.voice-setup').getBoundingClientRect().bottom<document.querySelector('.surface-dock').getBoundingClientRect().top),true,'Speaker controls fit above the dock');
    await page.locator('#voice-key-details summary').click();
    await page.locator('#voice-delete-key').click();
    await page.waitForFunction(()=>document.querySelector('#voice-toggle').disabled);
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('#voice-history-clear').click();
    await page.waitForFunction(()=>document.querySelectorAll('.voice-history-turn').length===0);
    assert.equal(sent.filter(x=>x.endpoint==='input').length,2);
    assert.deepEqual(errors,[]);
    assert.deepEqual(await page.evaluate(()=>window.qaCsp),[]);
    await page.locator('[data-page="home"]').click();
    current.busy=true;current.enabled=true;current.phase='speaking';
    await page.waitForFunction(()=>!document.querySelector('#jarvis-home').hidden);
    assert.equal(await page.evaluate(()=>{jarvisStatusFreshAt=Date.now()-6000;paintJarvisHome();return document.querySelector('#jarvis-home').hidden}),true,'Expired voice snapshots hide the HUD');
    await page.evaluate(()=>showPairing());
    assert.equal(await page.locator('#jarvis-home').isHidden(),true,'Unpairing removes private voice activity');
    console.log('Jarvis browser checks passed: setup, private key field, microphone dropdowns, toggle and navigation. All voice writes mocked. History, citations, follow-up, speaker/alert preferences, Iron Man theme and actual-phase HUD lifecycle/layout on all screens checked.');
  }finally{
    await page.evaluate(async()=>{await fetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'}})}).catch(()=>{});
    await context.close();await browser.close();
  }
})().catch(error=>{console.error(String(error.message).split('\n')[0]);process.exitCode=1});
