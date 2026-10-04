// UI writes are intercepted: QA never changes the owner's app registrations or launches apps.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1280,height:800},hasTouch:true}),page=await context.newPage();
  const errors=[],writes=[];page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{window.qaCsp=[];document.addEventListener('securitypolicyviolation',e=>qaCsp.push(e.violatedDirective))});
  const idleRest={instance:'f'.repeat(24),revision:0,serverTime:Date.now(),rest:false,displayAvailable:true,keepingAwake:false,alarm:null,message:'',audio:{ready:false,phase:'off',message:''}};
  await page.route('**/api/alarms',route=>{assert.equal(route.request().method(),'GET');return route.fulfill({json:idleRest})});
  await page.addInitScript(data=>{const Native=window.WebSocket;window.WebSocket=class extends Native{set onmessage(receive){super.onmessage=event=>{const packet=JSON.parse(event.data);packet.rest={...data,serverTime:packet.serverTime};receive({data:JSON.stringify(packet)})}}}},idleRest);
  const catalog=Array.from({length:24},(_,i)=>({id:`qa-app-${i}`,name:`App ${i+1}`,category:'QA',color:'#a9bacf',available:true,running:false}));
  const candidate={id:'detected-'+'a'.repeat(24),name:'Editor <test>'};
  const games=Array.from({length:8},(_,i)=>({id:`qa-game-${i}`,name:i===0?'A Long Game Name: The Complete Edition':`Game ${i+1}`,launcher:'Steam',artwork:null}));
  try{
    await page.route('**/api/apps',route=>route.fulfill({json:catalog}));
    await page.route('**/api/apps/detected',route=>route.request().headers()['x-g16-qa-native']==='1'?route.continue():route.fulfill({json:catalog.some(a=>a.id===candidate.id)?[]:[candidate]}));
    const mutate=route=>{
      const request=route.request();writes.push({method:request.method(),body:request.postDataJSON()});
      if(request.method()==='POST'){
        assert.deepEqual(request.postDataJSON(),{id:candidate.id});
        if(catalog.length>=25)return route.fulfill({status:409,json:{detail:'You can keep up to 25 apps.'}});
        catalog.push({...candidate,category:'Installed apps',color:'#a9bacf',available:true,running:false});
      }else if(request.method()==='DELETE'){
        const id=request.url().split('/').pop();catalog.splice(catalog.findIndex(app=>app.id===id),1);
      }else throw new Error('Unexpected app registration method');
      return route.fulfill({json:catalog});
    };
    await page.route('**/api/apps/shortcuts',mutate);await page.route('**/api/apps/shortcuts/*',mutate);
    await page.route('**/api/apps/launch',route=>{throw new Error('UI check must never launch apps')});
    await page.route('**/api/games',route=>route.fulfill({json:{games,warnings:[]}}));
    await page.goto('https://localhost:18761/#system');
    await page.waitForFunction(()=>state.auth?.local===true);
    await page.locator('#device-name').fill('App picker QA');
    await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());
    await page.locator('#pair-form button').click();
    await page.waitForFunction(()=>state.paired&&!appPickerLoading&&appPickerLoaded);
    // A real read verifies discovery without modifying registrations or exposing executable paths.
    const native=await page.evaluate(async()=>{const r=await fetch('/api/apps/detected',{headers:{'X-G16-QA-Native':'1'}});return {status:r.status,apps:await r.json()}});
    assert.equal(native.status,200);assert.equal(Array.isArray(native.apps),true);
    assert.equal(native.apps.every(app=>!Object.hasOwn(app,'target')&&!Object.hasOwn(app,'args')),true);
    await page.locator('#app-shortcut-select').selectOption(candidate.id);
    await page.locator('#app-shortcut-add').click();
    await page.waitForFunction(()=>state.apps.length===25&&!appPickerPending);
    assert.match(await page.locator('#app-shortcut-settings').innerText(),/25 \/ 25 apps/);
    assert.equal(await page.locator('#app-shortcut-add').isDisabled(),true);
    assert.equal(await page.locator('#app-shortcut-select').isDisabled(),true);
    assert.equal(await page.locator('#app-shortcut-settings script').count(),0);
    await page.evaluate(()=>goPage('apps'));
    assert.equal(await page.locator('[data-app]').count(),25);
    assert.match(await page.locator('.apps-surface').innerText(),/Editor <test>/);
    await page.evaluate(()=>goPage('system'));
    await page.locator(`[data-remove-app="${candidate.id}"]`).click();
    await page.waitForFunction(()=>state.apps.length===24&&!appPickerPending&&!appPickerLoading);
    assert.equal(await page.locator('#app-shortcut-select').isEnabled(),true);
    const savedOwner=await page.evaluate(()=>state.auth.owner);
    await page.evaluate(()=>{state.auth.owner=false;render()});
    assert.equal(await page.locator('#app-shortcut-select').count(),0);
    assert.match(await page.locator('#app-shortcut-settings').innerText(),/approved Windows browser/);
    await page.evaluate(owner=>{state.auth.owner=owner;render()},savedOwner);
    for(const [width,height] of [[1280,800],[1280,720],[1024,600],[960,600],[800,1280],[768,1024],[600,960],[412,915],[640,400]]){
      await page.setViewportSize({width,height});await page.evaluate(()=>goPage('system'));
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`App settings fit ${width}×${height}`);
      await page.evaluate(()=>goPage('games'));await page.waitForFunction(()=>document.querySelectorAll('.game-card').length===8);
      const layout=await page.evaluate(()=>{const el=document.querySelector('.game-card');const r=el.getBoundingClientRect(),button=el.querySelector('button').getBoundingClientRect(),dock=document.querySelector('.surface-dock').getBoundingClientRect();return {width:r.width,height:r.height,touch:button.width>=44&&button.height>=44,aboveDock:r.bottom<dock.top||innerHeight<=500}});
      assert.equal(layout.width<=250,true,`Smaller covers at ${width}×${height}`);
      assert.equal(layout.height<=350,true,`Cover height ${JSON.stringify(layout)} at ${width}×${height}`);assert.equal(layout.touch,true,`Touch target ${JSON.stringify(layout)} at ${width}×${height}`);assert.equal(layout.aboveDock,true,`Dock clearance ${JSON.stringify(layout)} at ${width}×${height}`);
    }
    await page.setViewportSize({width:1280,height:800});
    fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
    await page.screenshot({path:path.join(root,'artifacts/games-smaller.png'),fullPage:true});
    await page.evaluate(()=>goPage('system'));await page.locator('.app-settings').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(root,'artifacts/app-picker-settings.png'),fullPage:true});
    assert.deepEqual(writes.map(write=>write.method),['POST','DELETE']);assert.deepEqual(errors,[]);assert.deepEqual(await page.evaluate(()=>qaCsp),[]);
    console.log('App picker and game layout checks passed: owner controls, detected ID-only add/remove, 25-app limit, escaped names, tablet read-only guidance, 25 Apps tiles, and smaller covers at nine touch sizes. All app writes mocked.');
  }finally{
    await page.evaluate(async()=>{await fetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'}})}).catch(()=>{});
    await context.close();await browser.close();
  }
})().catch(error=>{console.error(error.stack);process.exitCode=1});
