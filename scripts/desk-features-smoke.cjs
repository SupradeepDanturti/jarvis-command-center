// Trusted fresh QA browser. All timer/sensor/player writes are mocked; only QA logout is real.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1280,height:800},hasTouch:true});
 const page=await context.newPage(),errors=[],requests=[];
 page.on('pageerror',error=>errors.push(error.message));
 page.on('console',message=>{if(message.type()==='error'&&/Content Security Policy|Refused/i.test(message.text()))errors.push(message.text())});
 const root=path.resolve(__dirname,'..');fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
 let focus={settings:{focus:25,short:5,long:15,announcements:false},status:'ready',phase:'focus',remaining:1500,revision:0,completed:0,serverTime:Date.now()/1000};
 const media={available:true,status:'playing',player:'brave.exe',title:'A soundtrack for your evening',artist:'Desk sessions',album:'A quieter moment',sessionId:'a'.repeat(24),trackRevision:'b'.repeat(24),controls:{'play-pause':true,previous:true,next:true,seek:true},timeline:{start:0,end:240,position:30,rate:1},artwork:'/api/media/artwork/'+ 'b'.repeat(24)};
 try{
  await page.goto(process.env.G16_BASE_URL||'https://localhost:18761');await page.waitForFunction(()=>state.auth?.local);
  await page.locator('#device-name').fill('Desk features QA');await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());await page.locator('#pair-form button').click();await page.waitForFunction(()=>state.paired&&!state.stale);
  await page.evaluate(()=>goPage('media'));await page.screenshot({path:path.join(root,'artifacts/media-native.png')});
  await page.route('**/api/media/**',async route=>{
   if(route.request().method()==='GET')return route.request().url().includes('/artwork/')?route.fulfill({path:path.join(root,'frontend/assets/event-horizon.jpg'),contentType:'image/jpeg'}):route.fulfill({json:{...media,sampledAt:Date.now()}});
   requests.push({url:route.request().url(),body:route.request().postDataJSON()});return route.fulfill({json:{ok:true}});
  });
  await page.route('**/api/focus**',async route=>{
   if(route.request().method()!=='GET'){
    const body=route.request().postDataJSON();requests.push({url:route.request().url(),body});if(body.revision!==focus.revision)return route.fulfill({status:409,json:{detail:'QA timer revision conflict'}});
    if(body.action==='start'||body.action==='resume')focus.status='running';
    else if(body.action==='pause')focus.status='paused';else if(body.action==='reset'){focus.status='ready';focus.remaining=1500}
    else if(!body.action)focus.settings={focus:body.focus,short:body.short,long:body.long,announcements:body.announcements};
    focus.revision++;
   }
   focus.serverTime=Date.now()/1000;await page.evaluate(data=>{window.qaFocus=data},focus);return route.fulfill({json:focus});
  });
  await page.route('**/api/thermals/**',route=>route.fulfill({json:{settings:{enabled:false,cpuTemperature:null,cpuThrottle:null,gpuThrottle:null,fans:[],drives:[]},readings:[],reason:'Extra sensors off'}}));
  await page.evaluate(({media,focus})=>{
   window.qaMedia=media;window.qaFocus=focus;
   const receive=state.socket.onmessage;
   state.socket.onmessage=event=>{const packet=JSON.parse(event.data);packet.media={...window.qaMedia,sampledAt:packet.serverTime};packet.focus={...window.qaFocus,serverTime:packet.serverTime/1000};packet.activity={game:null,sampledAt:packet.serverTime};receive({data:JSON.stringify(packet)})};
   state.playback=null;focusState=null;updateMediaPlayback({...media,sampledAt:Date.now()});acceptFocus(focus);render();
  },{media,focus});
  await page.waitForFunction(()=>document.querySelector('#media-art').complete&&document.querySelector('#media-art').naturalWidth>0);
  assert.equal(await page.locator('#media-title').innerText(),media.title);assert.equal(await page.locator('#media-player').innerText(),'Brave');
  assert.equal(await page.locator('.media-volume button').count(),3);
  assert.match(await page.locator('[data-media="volume-down"] svg').innerHTML(),/a5 5/);
  assert.match(await page.locator('[data-media="volume-up"] svg').innerHTML(),/a9 9/);
  for(const action of ['volume-down','mute','volume-up'])await page.locator(`[data-media="${action}"]`).click();
  assert.deepEqual(requests.splice(0).map(request=>request.url.split('/').pop()),['volume-down','mute','volume-up']);
  await page.locator('[data-session-action="play-pause"]').click();assert.equal(requests.splice(0)[0].body.action,'play-pause');
  const slider=page.locator('#media-seek');await slider.focus();await page.keyboard.press('ArrowRight');await page.waitForTimeout(100);
  const seek=requests.splice(0);assert.equal(seek.length,1);assert.equal(seek[0].body.sessionId,media.sessionId);assert.ok(seek[0].body.position>30);
  await page.evaluate(()=>{window.qaMedia.title='<img src=x onerror=alert(1)>';window.qaMedia.artist='An artist with a long name';updateMediaPlayback({...window.qaMedia,sampledAt:Date.now()})});
  assert.equal(await page.locator('#media-title img').count(),0);assert.equal(await page.locator('#media-title').innerText(),'<img src=x onerror=alert(1)>');
  await page.evaluate(()=>{window.qaMedia.title='A soundtrack for your evening';window.qaMedia.artist='Desk sessions';updateMediaPlayback({...window.qaMedia,sampledAt:Date.now()})});
  for(const [width,height] of [[1280,800],[1280,720],[1024,600],[960,600],[800,1280],[768,1024],[600,960],[412,915],[640,400]]){
   await page.setViewportSize({width,height});await page.evaluate(()=>goPage('media'));await page.waitForTimeout(100);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Media overflow ${width}x${height}`);
   for(const selector of ['[data-session-action]','.media-volume button','#media-seek']){
    for(const button of await page.locator(selector).all()){const box=await button.boundingBox();assert.ok(box.height>=44,`Touch height ${width}x${height}`)}
   }
   const dock=await page.locator('.surface-dock').boundingBox(),volume=await page.locator('.media-volume').boundingBox();
   assert.ok(volume.y+volume.height<=dock.y||volume.y>=dock.y+dock.height,`Volume/dock overlap ${width}x${height}`);
   if(width===1280&&height===800||width===800&&height===1280)await page.screenshot({path:path.join(root,`artifacts/media-${width}x${height}.png`),fullPage:true});
   await page.evaluate(()=>{focusView=true;goPage('clock')});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Focus overflow ${width}x${height}`);
  }
  await page.setViewportSize({width:1280,height:800});await page.locator('[data-focus-action="start"]').click();await page.waitForFunction(()=>focusState.status==='running');
  await page.locator('[data-focus-action="pause"]').click();await page.waitForFunction(()=>focusState.status==='paused');
  await page.locator('[data-focus-action="resume"]').click();await page.waitForFunction(()=>focusState.status==='running');
  page.once('dialog',dialog=>dialog.accept());await page.locator('[data-focus-action="reset"]').click();await page.waitForFunction(()=>focusState.status==='ready');
  await page.screenshot({path:path.join(root,'artifacts/focus-1280x800.png')});
  await page.evaluate(()=>goPage('system'));
  await page.locator('#display-behavior-settings input[name="rotation"]').check();await page.locator('#display-behavior-settings button[type=submit]').click();assert.equal(await page.evaluate(()=>displayBehavior.preferences.rotation),true);
  await page.reload();await page.waitForFunction(()=>state.paired&&!state.stale);assert.equal(await page.evaluate(()=>displayBehavior.preferences.rotation),true,'Browser display preferences persist');
  await page.evaluate(()=>{displayBehavior.configure({});localStorage.removeItem('g16-display-behavior');goPage('hardware')});await page.waitForSelector('#thermal-settings',{state:'attached'});
  assert.match(await page.locator('[data-thermal-reason]').innerText(),/off|unavailable/i);assert.equal(await page.locator('[data-thermal-readings]').getByText('Unavailable',{exact:true}).count(),5);
  assert.deepEqual(errors,[]);console.log('Desk features passed: Now playing artwork/layout, escaped metadata, session controls/seek, volume, focus controls, preference persistence, unavailable sensors, nine viewports, trusted HTTPS and no page/CSP errors.');
 }finally{
  if(await page.evaluate(()=>state.paired).catch(()=>false))await page.evaluate(async()=>{
   // Clean this script's QA identities left by an interrupted run, never user devices.
   if(state.auth?.owner)for(const device of await api('/api/devices'))if(device.name==='Desk features QA'&&device.id!==state.auth.device.id)await api(`/api/devices/${device.id}/revoke`,{method:'POST'});
   await api('/api/logout',{method:'POST'});
  }).catch(()=>{});
  await context.close();await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1});
