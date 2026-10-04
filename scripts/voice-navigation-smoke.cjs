// Fresh trusted QA browser. Voice, widget data and Rest are fixtures; no physical actions are sent.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1280,height:800},hasTouch:true});
  const page=await context.newPage(),errors=[],writes=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{window.qaCsp=[];document.addEventListener('securitypolicyviolation',e=>qaCsp.push(e.violatedDirective))});
  const rest={instance:'e'.repeat(24),revision:0,serverTime:Date.now(),rest:false,displayAvailable:true,keepingAwake:false,alarm:null,message:'',audio:{ready:false,phase:'off',message:''}};
  await page.route('**/api/alarms',route=>route.fulfill({json:rest}));
  await page.addInitScript(data=>{
    const Native=window.WebSocket;
    window.WebSocket=class extends Native{
      set onmessage(receive){super.onmessage=event=>{const packet=JSON.parse(event.data);packet.rest={...data,serverTime:packet.serverTime};receive({data:JSON.stringify(packet)})}}
    };
  },rest);
  let serial=1;
  const current={phase:'listening',message:'Wake word armed.',busy:true,enabled:true,ready:true,
    keyConfigured:true,modelsInstalled:true,dependenciesInstalled:true,lastHeard:'',lastReply:'',
    inputId:null,outputId:null,alertsEnabled:true,followupSeconds:15,history:[],serverTime:Date.now(),
    navigation:{id:String(serial).padStart(24,'0'),screen:'games',expiresAt:Date.now()+10000}};
  await page.route('**/api/voice/**',route=>{
    assert.equal(route.request().method(),'GET','QA must not change the real voice configuration');
    const endpoint=route.request().url().split('/').pop().split('?')[0];
    return route.fulfill({json:endpoint==='status'?{...current,serverTime:Date.now()}:[]});
  });
  await page.route('**/api/widgets/**',route=>route.fulfill({json:{status:'unavailable',data:null,fetchedAt:null,serverTime:Date.now()/1000}}));
  page.on('request',request=>{
    if(request.url().includes('/api/')&&request.method()!=='GET')writes.push(new URL(request.url()).pathname);
  });
  async function send(screen,extra={}){
    current.navigation={id:String(++serial).padStart(24,'0'),screen,expiresAt:Date.now()+10000,...extra};
    await page.evaluate(()=>refreshVoice());
    await page.waitForFunction(id=>voiceState?.navigation?.id===id,current.navigation.id);
  }
  async function view(id){
    try{await page.waitForFunction(id=>state.page===id,id,{timeout:5000})}
    catch(error){throw new Error(`Expected ${id}: ${JSON.stringify(await page.evaluate(()=>({page:state.page,stale:state.stale,baseline:voiceNavigationReady,id:voiceNavigationId,phase:voiceState?.phase,errors:qaCsp})))}`)}
  }
  try{
    await page.goto('https://localhost:18761/#home');await page.waitForFunction(()=>state.auth?.local===true);
    await page.locator('#device-name').fill('Voice navigation QA');
    await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());
    await page.locator('#pair-form button').click();
    await page.waitForFunction(()=>state.paired&&!state.stale&&voiceNavigationReady);
    assert.equal(await page.evaluate(()=>state.page),'home','Initial snapshot must not replay a request');
    const screens=await page.evaluate(()=>Object.keys(pages));
    for(const screen of screens){await send(screen);await view(screen==='widgets'?'system':screen)}
    await send('focus');await view('clock');assert.equal(await page.evaluate(()=>focusView),true);
    await send('clock');assert.equal(await page.evaluate(()=>focusView),false);
    await send('weather');await view('system');
    assert.equal(await page.evaluate(()=>widgetPreferences.weather),false,'Voice must not enable online widgets');
    await page.evaluate(()=>{widgetPreferences.weather=true;widgetPreferences.location=null;saveWidgetPreferences()});
    await send('weather');await view('system');
    await page.evaluate(()=>{widgetPreferences.location={name:'Toronto',latitude:43.7,longitude:-79.4};saveWidgetPreferences()});
    await send('weather');await view('widgets');assert.equal(await page.locator('.widget-screen').getAttribute('data-widget-view'),'weather');
    await send('f1');await view('system');assert.equal(await page.evaluate(()=>widgetPreferences.f1),false);
    await page.evaluate(()=>{widgetPreferences.f1=true;saveWidgetPreferences()});
    await send('f1');await view('widgets');assert.equal(await page.locator('.widget-screen').getAttribute('data-widget-view'),'f1');
    await page.evaluate(()=>goPage('home'));await page.evaluate(()=>refreshVoice());await view('home');
    await page.reload();await page.waitForFunction(()=>state.paired&&!state.stale&&voiceNavigationReady);await view('home');
    for(const [screen,extra] of [['games',{expiresAt:Date.now()-1}],['https://evil.example',{}],['games',{id:'invalid'}]]){
      await send(screen,extra);await view('home');
    }
    for(const phase of ['locked','off','preview','error']){
      current.phase=phase;await send('games');await view('home');
    }
    current.phase='listening';current.enabled=false;await send('games');await view('home');current.enabled=true;
    await page.evaluate(()=>{restState.rest=true});await send('games');await view('home');await page.evaluate(()=>{restState.rest=false});
    await page.evaluate(()=>{document.querySelector('#alarm-editor').showModal()});await send('games');await view('home');
    await page.evaluate(()=>document.querySelector('#alarm-editor').close());
    await page.evaluate(()=>{setConnection(false,'QA disconnected')});
    await send('games');await view('home');
    await page.waitForFunction(()=>!state.stale);await page.evaluate(()=>refreshVoice());await view('home');
    await send('clock');await view('clock');
    await page.evaluate(()=>setPresentation(true));await send('apps');await view('apps');assert.equal(await page.evaluate(()=>presentation),false);
    // Voice navigation starts the same manual hold used by touch, even with rotation enabled.
    await page.evaluate(()=>displayBehavior.configure({rotation:true,dwell:30,pages:['home','clock']}));
    await send('clock');await view('clock');
    assert.equal(await page.evaluate(()=>displayBehavior.tick({page:'clock',ready:true,widgetsEnabled:true})),null);
    // A hidden browser ignores requests; returning establishes a baseline rather than replaying them.
    await page.evaluate(()=>{
      Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});
      document.dispatchEvent(new Event('visibilitychange'));
    });
    current.navigation={id:String(++serial).padStart(24,'0'),screen:'games',expiresAt:Date.now()+10000};
    await page.evaluate(status=>acceptVoiceNavigation(status),{...current,serverTime:Date.now()});
    await page.evaluate(()=>{
      Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.evaluate(()=>refreshVoice());
    await page.waitForFunction(id=>voiceState?.navigation?.id===id,current.navigation.id);
    await view('clock');await send('home');await view('home');
    // Scene IDs come from the display catalog, not this test's fixed list.
    const catalog=await page.evaluate(()=>ambientScenes),sceneIds=Object.keys(catalog);
    assert.equal(sceneIds.length>0,true);
    await page.evaluate(()=>{screenPreferences.motion=false;saveScreenPreferences()});
    for(const scene of sceneIds){
      await send('ambient',{scene});await view('ambient');
      assert.equal(await page.locator('.ambient-screen').getAttribute('data-scene'),scene);
      assert.equal(await page.locator('#scene-name').innerText(),catalog[scene].name);
      assert.equal(await page.locator('#ambient-video').getAttribute('data-scene'),scene);
      assert.equal(await page.locator('#ambient-video').evaluate(video=>video.paused),true,'Voice preserves pause');
    }
    await page.locator(`[data-scene-select="${sceneIds[0]}"]`).click();
    await page.evaluate(()=>refreshVoice());
    assert.equal(await page.evaluate(()=>screenPreferences.scene),sceneIds[0],'A repeated voice status cannot undo a scene chosen by touch');
    await send('ambient');assert.equal(await page.evaluate(()=>screenPreferences.scene),sceneIds[0],'Plain Ambient keeps the selected scene');
    await page.evaluate(()=>goPage('home'));
    await send('ambient',{scene:'https://evil.example/movie'});await view('home');
    await send('games',{scene:sceneIds[0]});await view('home');
    await page.reload();await page.waitForFunction(()=>state.paired&&!state.stale&&voiceNavigationReady);
    assert.equal(await page.evaluate(()=>screenPreferences.scene),sceneIds[0],'Scene choice persists on this QA browser');
    // A previously unknown catalog option uses the same generic selector and escaped captions.
    const added={...catalog,["qa-new-scene"]:{...catalog[sceneIds[0]],number:'05 /',name:'New catalog option',description:'<img src=x onerror=alert(1)>',credit:'Fixture <credit>'}};
    let servedCatalog=added;
    await page.route('**/static/ambient-scenes.js*',route=>route.fulfill({contentType:'application/javascript',body:'const ambientScenes='+JSON.stringify(servedCatalog)+';'}));
    await page.reload();await page.waitForFunction(()=>state.paired&&!state.stale&&voiceNavigationReady);
    await send('ambient',{scene:'qa-new-scene'});await view('ambient');
    assert.equal(await page.locator('[data-scene-select="qa-new-scene"]').innerText(),'New catalog option');
    assert.equal(await page.locator('#scene-name').innerText(),'New catalog option');
    assert.equal(await page.locator('#scene-description').innerText(),added['qa-new-scene'].description);
    assert.equal(await page.locator('.ambient-caption img').count(),0,'Catalog captions remain text');
    servedCatalog={};await page.reload();await page.waitForFunction(()=>state.paired&&!state.stale&&voiceNavigationReady);
    await send('ambient');await view('ambient');
    assert.match(await page.locator('.ambient-screen').innerText(),/unavailable/);
    assert.equal(await page.locator('#ambient-video').count(),0,'An empty catalog does not invent a playable scene');
    assert.deepEqual(errors,[]);assert.deepEqual(await page.evaluate(()=>qaCsp),[]);
    assert.deepEqual(writes.filter(endpoint=>!['/api/pair','/api/device/activate','/api/device/display','/api/widgets/weather','/api/widgets/air-quality'].includes(endpoint)),[],
      'Opening screens must not launch apps/games, change settings, start timers or control physical devices');
    console.log('Voice navigation passed: all pages, weather/F1 consent, Focus, all catalog scenes and a new scene, preserved pause/choice, escaped captions, empty catalog, once-only delivery, reload/hide/reconnect baselines, expiry/allowlist, lock/off/Rest/dialog guards, immersive exit and manual hold; no physical writes or CSP/page errors.');
  }finally{
    if(!page.isClosed())await page.evaluate(()=>fetch('/api/logout',{method:'POST'})).catch(()=>{});
    await context.close();await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
