// Trusted fresh-profile QA. All assistant reads/writes and Google navigation are fixtures.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..'),artifacts=path.join(root,'artifacts');fs.mkdirSync(artifacts,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});let context,page;
  try{
    context=await browser.newContext({viewport:{width:1280,height:800}});page=await context.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error'&&/Content Security Policy|Refused/i.test(message.text()))errors.push(message.text())});
    await page.goto(process.env.G16_BASE_URL||'https://localhost:18761');
    await page.waitForFunction(()=>state.auth?.local===true);await page.locator('#device-name').fill('Assistant smoke check');await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());await page.locator('#pair-form button').click();await page.waitForFunction(()=>state.paired&&state.auth?.owner);
    let status={enabled:false,clientConfigured:false,account:null,calendarReady:false,connecting:false,grantedScopes:[],message:''};
    let profile={address:'sir',timezone:'America/Toronto',tone:'jarvis'};let releaseToday;
    const methods=[];
    await context.route('https://accounts.google.com/**',route=>route.fulfill({contentType:'text/plain',body:'Google sign-in fixture — no real account access.'}));
    await page.route('**/api/assistant/**',async route=>{
      const request=route.request(),url=new URL(request.url()),endpoint=url.pathname.split('/api/assistant/')[1];methods.push([endpoint,request.method()]);let body;
      if(endpoint==='status')body=status;
      else if(endpoint==='enabled'){status={...status,enabled:request.postDataJSON().enabled,connecting:false};body=status}
      else if(endpoint==='google/client'&&request.method()==='PUT'){assert.equal(typeof request.postDataJSON().contents,'string');status={...status,clientConfigured:true};body=status}
      else if(endpoint==='google/connect'){status={...status,connecting:true};body={url:'https://accounts.google.com/o/oauth2/v2/auth?fixture=1',expiresIn:300}}
      else if(endpoint==='google/connection'){status={...status,account:null,connecting:false,calendarReady:false};body=status}
      else if(endpoint==='profile'){if(request.method()==='PUT')profile=request.postDataJSON();if(request.method()==='DELETE')profile={address:'sir',timezone:'America/Toronto',tone:'jarvis'};body=profile}
      else if(endpoint==='today'){
        if(releaseToday)await new Promise(resolve=>releaseToday=resolve);
        body={day:'2026-10-04',timezone:profile.timezone,calendar:'primary',partial:false,message:`Today's primary calendar checked, ${profile.address}. 2 events found.`,events:[{title:'<img src=x onerror=alert(1)>',start:'2026-10-04',end:'2026-10-05',allDay:true},{title:'Planning',start:'2026-10-04T14:00:00Z',end:'2026-10-04T15:00:00Z',allDay:false}]};
      }else throw new Error('Unmocked assistant endpoint: '+endpoint);
      await route.fulfill({json:body});
    });
    async function screen(id){await page.evaluate(id=>goPage(id),id);await page.waitForTimeout(150)}
    await screen('connections');assert.equal(await page.locator('#page-content .card').count(),0);assert.equal(await page.locator('[data-google-connect]').isDisabled(),true);
    await page.locator('.assistant-setup summary').click();await page.locator('#google-client-file').setInputFiles({name:'desktop-client.json',mimeType:'application/json',buffer:Buffer.from('{"installed":{"client_id":"fixture"}}')});
    await page.waitForFunction(()=>document.querySelector('#google-client-file').value===''&&document.querySelector('[data-assistant-toggle]').textContent==='Enable assistant');
    await page.locator('[data-assistant-toggle]').click();await page.waitForFunction(()=>!document.querySelector('[data-google-connect]').disabled);
    const popupPromise=context.waitForEvent('page');await page.locator('[data-google-connect]').click();const popup=await popupPromise;await popup.waitForLoadState();assert.match(await popup.locator('body').innerText(),/no real account/);await popup.close();
    status={...status,connecting:false,account:{email:'qa@example.test'},calendarReady:true};await screen('personalization');
    await page.locator('[name=address]').fill('Supradeep');await page.locator('[name=timezone]').fill('Asia/Kolkata');await page.locator('[name=tone]').selectOption('jarvis');await page.locator('#assistant-profile [type=submit]').click();await page.waitForFunction(()=>document.querySelector('#assistant-profile-note').textContent==='Preferences saved.');
    await screen('agenda');await page.locator('[data-assistant-today]').click();await page.locator('.assistant-events li').first().waitFor();assert.equal(await page.locator('.assistant-events li').count(),2);assert.equal(await page.locator('#assistant-agenda img').count(),0);assert.match(await page.locator('.assistant-briefing').innerText(),/Supradeep/);
    assert.equal(await page.evaluate(()=>Object.values(localStorage).some(value=>/qa@example|Supradeep|Planning/.test(value))),false);
    for(const [width,height,label] of [[1280,800,'landscape'],[800,1280,'portrait'],[390,844,'narrow']]){
      await page.setViewportSize({width,height});for(const id of ['connections','personalization','agenda']){await screen(id);assert.equal(await page.locator('#page-content').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true,`${id} ${label} must fit`);assert.equal(await page.locator('.surface-dock').isVisible(),true)}
      await page.screenshot({path:path.join(artifacts,`assistant-${label}.png`),fullPage:true});
    }
    await page.setViewportSize({width:1280,height:800});await screen('agenda');releaseToday=true;
    const late=page.waitForRequest(request=>request.url().endsWith('/api/assistant/today'));await page.locator('[data-assistant-today]').click();await late;await screen('connections');await page.locator('[data-assistant-toggle]').click();releaseToday();await page.waitForTimeout(200);assert.equal(await page.locator('#assistant-agenda').count(),0,'A late briefing must not appear on another screen');
    await screen('personalization');await page.locator('[data-assistant-forget]').click();await page.waitForFunction(()=>document.querySelector('[name=address]')?.value==='sir');
    await screen('agenda');await page.evaluate(()=>showPairing());assert.equal(await page.locator('#assistant-private').innerText(),'','Unpairing clears personal content');
    assert.deepEqual(errors,[]);assert(methods.some(([endpoint,method])=>endpoint==='google/client'&&method==='PUT'));
    console.log('Assistant smoke passed: owner UI, mocked OAuth, profile, private agenda, safe rendering, cancellation and responsive layouts.');
  }finally{
    if(page)try{await page.evaluate(async()=>{await fetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'}})})}catch{}
    if(context)await context.close();await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
