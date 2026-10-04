// Trusted, fresh QA profile. Every alarm/display/audio command is mocked.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1280,height:800},hasTouch:true,timezoneId:'America/Toronto'});
 const page=await context.newPage(),errors=[],writes=[];
 let mock={instance:'a'.repeat(24),revision:0,serverTime:Date.now(),rest:false,displayAvailable:true,keepingAwake:false,alarm:null,message:'',audio:{ready:true,phase:'off',message:''}};
 const sync=async()=>{mock.serverTime=Date.now();await page.evaluate(data=>{window.qaRest=data;acceptRest(data)},mock)};
 page.on('pageerror',error=>errors.push(error.message));
 page.on('console',message=>{if(message.type()==='error'&&/Content Security Policy|Refused/i.test(message.text()))errors.push(message.text())});
 await context.addInitScript(data=>{
  window.qaRest=data;const Native=window.WebSocket;
  window.WebSocket=class extends Native{
   set onmessage(receive){super.onmessage=event=>{const packet=JSON.parse(event.data);packet.rest={...window.qaRest,serverTime:packet.serverTime};receive({data:JSON.stringify(packet)})}}
  };
 },mock);
 await page.route(/\/api\/(alarms|rest)(\/|$)/,async route=>{
  const request=route.request(),url=new URL(request.url()).pathname;
  if(request.headers()['x-g16-qa-native']==='1'){
   assert.equal(url,'/api/rest/prepare');assert.equal(request.method(),'POST');return route.continue();
  }
  if(request.method()!=='GET'){
   const body=request.postData()?request.postDataJSON():null;writes.push({url,body});
   if(url==='/api/rest/prepare')return route.fulfill({json:{nonce:'b'.repeat(24)}});
   if(url==='/api/alarms/preview')assert.equal(body,null,'Preview has no arbitrary spoken input');
   else{
    if(url!=='/api/rest/wake'&&body.revision!==mock.revision)return route.fulfill({status:409,json:{detail:'Alarm changed on another screen.'}});
    if(url==='/api/alarms')mock.alarm={id:'c'.repeat(24),label:body.label,dueAt:body.dueAt,speech:body.speech,status:'armed',startedAt:null};
    if(url==='/api/rest/enter'){assert.equal(body.nonce,'b'.repeat(24));mock.rest=true}
    if(url==='/api/rest/wake')mock.rest=false;
    if(url==='/api/alarms/command'){
     if(body.action==='cancel')mock.alarm=null;
     if(body.action==='dismiss')mock.alarm.status='dismissed';
     if(body.action==='snooze'){mock.alarm.status='armed';mock.alarm.dueAt=Date.now()/1000+300;mock.alarm.startedAt=null}
    }
    mock.revision++;mock.keepingAwake=mock.rest||['armed','ringing'].includes(mock.alarm?.status);
   }
  }
  await sync();return route.fulfill({json:mock});
 });
 try{
  await page.goto(process.env.G16_BASE_URL||'https://localhost:18761/#rest');await page.waitForFunction(()=>state.auth?.local);
  await page.locator('#device-name').fill('Rest alarms QA');await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());await page.locator('#pair-form button').click();await page.waitForFunction(()=>state.paired&&!state.stale&&restReady());
  assert.equal(await page.locator('.rest-alarm-screen').count(),1,'Rest hash route renders');
  const server=await page.evaluate(async()=>{const response=await fetch('/api/alarms?qa=read');return {status:response.status,data:await response.json()}});assert.equal(server.status,200);assert.ok(Number.isInteger(server.data.revision),'Running backend has alarm endpoint');
  // Optional local hardware read: issue a QA-bound nonce but never send the enter request.
  if(process.env.G16_CHECK_DDC_READ==='1'){
   const prepared=await page.evaluate(async()=>{const start=performance.now(),response=await fetch('/api/rest/prepare',{method:'POST',headers:{'X-G16-QA-Native':'1'}}),body=await response.json();return {status:response.status,nonceValid:/^[0-9a-f]{24}$/.test(body.nonce||''),seconds:(performance.now()-start)/1000}});
   assert.equal(prepared.status,200);assert.equal(prepared.nonceValid,true);console.log(`Live read-only dock preparation passed in ${prepared.seconds.toFixed(2)} seconds; no enter/off command sent.`);
  }
  await page.locator('[data-alarm-editor]').click();await page.locator('#alarm-form input[name=label]').fill('<img src=x onerror=alert(1)>');
  await page.locator('#alarm-form [type=submit]').click();await page.waitForFunction(()=>restState.alarm?.status==='armed');
  assert.equal(writes.find(item=>item.url==='/api/alarms').body.speech,true);
  assert.equal(await page.locator('[data-rest-label] img').count(),0);
  assert.equal(await page.locator('[data-rest-label]').innerText(),mock.alarm.label);
  await page.locator('[data-alarm-editor]').click();await page.locator('[data-alarm-preview]').click();await page.waitForFunction(()=>!restPending);
  await page.locator('[data-alarm-close]').click();
  await page.evaluate(()=>goPage('media'));const original=await page.evaluate(()=>state.page);
  mock.rest=true;mock.revision++;await sync();
  assert.equal(await page.evaluate(()=>state.page),original,'Rest preserves current screen');
  assert.equal(await page.locator('.surface-navigation').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.querySelector('#surface-backdrop video')?.paused??true),true);
  await page.locator('[data-rest-brighten]').click();assert.equal(await page.evaluate(()=>document.body.classList.contains('rest-controls-bright')),true);
  await page.locator('[data-wake-displays]').click();await page.waitForFunction(()=>!restState.rest&&!restPending);assert.equal(await page.evaluate(()=>state.page),original);
  await page.evaluate(()=>goPage('rest'));
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('[data-enter-rest]').click();assert.equal(writes.filter(item=>item.url==='/api/rest/enter').length,0);
  page.once('dialog',dialog=>dialog.accept());await page.locator('[data-enter-rest]').click();await page.waitForFunction(()=>restState.rest&&!restPending&&!restPreparing);
  assert.equal(writes.filter(item=>item.url==='/api/rest/enter').length,1);
  mock.rest=false;mock.alarm={...mock.alarm,status:'ringing',startedAt:Date.now()/1000};mock.revision++;await sync();
  await page.waitForFunction(()=>document.querySelector('#alarm-ringing').open);
  await page.keyboard.press('Escape');assert.equal(await page.locator('#alarm-ringing').evaluate(el=>el.open),true);
  assert.equal(await page.locator('#alarm-spoken-label img').count(),0);
  await page.locator('#alarm-ringing [data-alarm-command=snooze]').click();await page.waitForFunction(()=>!restPending&&!document.querySelector('#alarm-ringing').open);assert.equal(mock.alarm.status,'armed');
  mock.alarm.status='ringing';mock.revision++;await sync();await page.locator('#alarm-ringing [data-alarm-command=dismiss]').click();await page.waitForFunction(()=>!restPending);assert.equal(mock.alarm.status,'dismissed');
  await page.reload();await page.waitForFunction(()=>state.paired&&!state.stale&&restReady());await sync();assert.equal(await page.locator('[data-rest-label]').innerText(),mock.alarm.label);
  for(const [width,height] of [[1280,800],[1280,720],[1024,600],[960,600],[800,1280],[768,1024],[600,960],[412,915],[640,400]]){
   await page.setViewportSize({width,height});await page.evaluate(()=>goPage('rest'));
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Rest overflow ${width}x${height}`);
   for(const button of await page.locator('.rest-actions button:visible').all())assert.ok((await button.boundingBox()).height>=44);
   const dock=await page.locator('.surface-dock').boundingBox();
   for(const button of await page.locator('.rest-actions button:visible').all()){
    if(height<560)await button.evaluate(el=>el.scrollIntoView({block:'center'}));
    const box=await button.boundingBox();assert.ok(box.y+box.height<=dock.y||box.y>=dock.y+dock.height,`Rest/dock overlap ${width}x${height}`);
   }
   await page.evaluate(()=>scrollTo(0,0));
   if(width===1280&&height===800||width===800&&height===1280)await page.screenshot({path:path.join(root,`artifacts/rest-${width}x${height}.png`),fullPage:true});
   await page.locator('[data-alarm-editor]').click();
   const dialogFits=await page.evaluate(()=>document.querySelector('#alarm-editor').scrollWidth<=document.querySelector('#alarm-editor').clientWidth+1);
   if(!dialogFits){await page.screenshot({path:path.join(root,'artifacts/alarm-layout-failure.png')});console.log(await page.locator('#alarm-editor').evaluate(el=>({client:el.clientWidth,scroll:el.scrollWidth,children:[...el.querySelectorAll('*')].filter(item=>item.scrollWidth>item.clientWidth+1).map(item=>({tag:item.tagName,class:item.className,width:item.clientWidth,scroll:item.scrollWidth}))})))}
   assert.ok(dialogFits,`Dialog overflow ${width}x${height}`);
   await page.locator('[data-alarm-close]').click();
   mock.rest=true;mock.revision++;await sync();assert.equal(await page.locator('.surface-navigation').isVisible(),false);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Dim overflow ${width}x${height}`);
   mock.rest=false;mock.revision++;await sync();
  }
  await page.setViewportSize({width:1280,height:800});await page.locator('[data-alarm-editor]').click();
  await page.locator('#alarm-form input[name=day]').fill('2027-03-14');await page.locator('#alarm-form input[name=time]').fill('02:30');await page.locator('#alarm-form [type=submit]').click();assert.match(await page.locator('#alarm-form-error').innerText(),/valid local time/);await page.locator('[data-alarm-close]').click();
  await page.evaluate(()=>{restReceipt=performance.now()-6000;paintRest()});assert.equal(await page.locator('[data-enter-rest]').isDisabled(),true);await sync();
  await page.locator('[data-alarm-command=cancel]').click();await page.waitForFunction(()=>!restPending);assert.equal(mock.alarm,null);
  assert.deepEqual(errors,[]);console.log('Rest alarms passed: hash route, shared state/reload, confirmed one-shot entry, dim/wake, fixed preview, escaped labels, ringing/snooze/dismiss/cancel, DST rejection, freshness, nine touch viewports, trusted HTTPS. No physical power/audio actions.');
 }finally{
  if(await page.evaluate(()=>state.paired).catch(()=>false))await page.evaluate(async()=>{
   if(state.auth?.owner)for(const device of await api('/api/devices'))if(device.name==='Rest alarms QA'&&device.id!==state.auth.device.id)await api(`/api/devices/${device.id}/revoke`,{method:'POST'});
   await api('/api/logout',{method:'POST'});
  }).catch(()=>{});
  await context.close();await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1});
