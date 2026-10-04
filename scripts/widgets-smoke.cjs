// Fresh QA browser; provider fixtures do not alter the owner's preferences or controls.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..');fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1280,height:800},hasTouch:true});
  const page=await context.newPage(),errors=[],calls=[];
  const external=[];page.on('request',request=>{if(!request.url().startsWith('https://localhost:18761/')&&!request.url().startsWith('wss://localhost:18761/'))external.push(request.url())});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error'&&/Content Security Policy|Refused/i.test(message.text()))errors.push(message.text())});
  const voice={phase:'listening',busy:true,enabled:true,message:'Working on your request.',lastReply:'At your service, sir.'};
  await page.route('**/api/voice/status',route=>route.fulfill({json:voice}));
  let failures=false,delayed=false,releaseWeather;
  const makeFeed=data=>({status:'ready',fetchedAt:Date.now()/1000,serverTime:Date.now()/1000,data});
  await page.route('**/api/widgets/**',async route=>{
    const kind=route.request().url().split('/').pop();calls.push(kind);
    if(failures&&kind!=='locations'){await route.fulfill({json:{status:'unavailable',data:null,fetchedAt:null,serverTime:Date.now()/1000}});return}
    if(delayed&&kind==='weather'){await new Promise(resolve=>{releaseWeather=resolve})}
    const now=Date.now()/1000;
    const data={
      locations:{locations:[{name:'Toronto, Ontario, Canada',latitude:43.7,longitude:-79.4},{name:'<img src=x onerror=alert(1)>',latitude:43,longitude:-79}]},
      weather:{observedAt:now,timezone:'America/Toronto',temperature:14,feelsLike:12,wind:8,humidity:65,code:3,days:[0,1,2].map(offset=>({time:now+offset*86400,high:18,low:8,rain:25,sunrise:now-3600,sunset:now+3600}))},
      'air-quality':{observedAt:now,aqi:42,pm25:6,pm10:9},
      f1:{race:{name:'Canadian Grand Prix',circuit:'Circuit Gilles-Villeneuve',location:'Montréal, Canada',start:now+123456,qualifying:now+23456}}
    };
    await route.fulfill({json:makeFeed(data[kind])});
  });
  async function screen(id){await page.evaluate(id=>goPage(id),id);await page.waitForFunction(id=>document.body.dataset.view===id,id);await page.evaluate(()=>scrollTo(0,0))}
  async function settings(){await screen('system');await page.locator('#widget-settings').scrollIntoViewIfNeeded()}
  async function layout(label){
    await page.evaluate(()=>scrollTo(0,0));
    const result=await page.evaluate(()=>{
      const dock=document.querySelector('.surface-dock').getBoundingClientRect();
      const elements=[...document.querySelectorAll('#page-content button,#page-content select,.native-digits,.analog-face,.moon-composition,.weather-temperature,.weather-air,.race-countdown')];
      return {overflow:document.documentElement.scrollWidth>innerWidth,
        overlaps:elements.filter(el=>{const r=el.getBoundingClientRect();return r.width&&r.height&&r.top<dock.bottom&&r.bottom>dock.top&&r.left<dock.right&&r.right>dock.left&&(!el.closest('.widget-content')||r.top<document.querySelector('.widget-content').getBoundingClientRect().bottom)}).map(el=>el.className||el.textContent),
        touch:elements.filter(el=>el.matches('button,select')&&getComputedStyle(el).display!=='none').every(el=>el.getBoundingClientRect().height>=44)};
    });
    assert.equal(result.overflow,false,label+' horizontal overflow');
    if(result.overlaps.length)await page.screenshot({path:path.join(root,'artifacts/widgets-layout-failure.png')});
    assert.deepEqual(result.overlaps,[],label+' dock overlap');
    assert.equal(result.touch,true,label+' touch target');
    if(await page.locator('.widget-screen').count()){
      const fit=await page.evaluate(()=>{
        const rect=selector=>document.querySelector(selector).getBoundingClientRect();
        const screen=rect('.widget-screen'),header=rect('.widget-screen>.screen-kicker'),content=rect('.widget-content'),footer=rect('.widget-screen>.screen-bottom');
        const hud=document.querySelector('#jarvis-home'),voice=hud.hidden?null:hud.getBoundingClientRect();
        const dock=rect('.surface-dock');
        return {page:document.documentElement.scrollHeight<=innerHeight+1,controls:header.top>=0&&footer.bottom<=screen.bottom+1&&screen.bottom<=(presentation?innerHeight:dock.top),space:content.height>0&&content.top>=header.bottom&&content.bottom<=footer.top,voice:!voice||(voice.top>=header.bottom&&voice.bottom<=content.top&&voice.left>=screen.left&&voice.right<=screen.right),exit:!presentation||rect('[data-screen-exit]').bottom<=header.bottom};
      });
      for(const [key,ok] of Object.entries(fit))assert.equal(ok,true,label+' '+key);
    }
  }
  try{
    await page.goto('https://localhost:18761');await page.waitForFunction(()=>state.auth?.local===true);
    await page.locator('#device-name').fill('Optional widgets QA');
    await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());
    await page.locator('#pair-form button').click();await page.waitForFunction(()=>state.paired&&!state.stale);
    assert.equal(await page.locator('[data-page="widgets"]').isVisible(),false);
    await screen('clock');assert.equal(await page.locator('.flip-clock').count(),1);assert.deepEqual(calls,[]);
    await settings();
    await page.locator('#widget-settings [name=clocks]').check();await page.locator('#widget-settings [name=clock]').selectOption('minimal');
    await page.locator('#widget-settings [name=weather]').check();await page.locator('#widget-settings [name=f1]').check();
    await page.locator('#widget-location-search input').fill('Toronto');await page.locator('#widget-location-search button').click();
    await page.locator('[data-widget-location="0"]').waitFor();assert.equal(await page.locator('#widget-location-results img').count(),0,'Provider text is escaped');
    await page.locator('[data-widget-location="0"]').click();assert.equal(await page.locator('#widget-settings [name=weather]').isChecked(),true,'City selection retains unsaved toggles');
    await page.locator('#widget-settings button[type=submit]').click();assert.deepEqual(calls,['locations'],'Enabling alone does not fetch data');
    await screen('widgets');await page.waitForFunction(()=>document.querySelector('[data-widget-temperature]').textContent==='14');
    assert.match(await page.locator('.widget-screen').innerText(),/Model estimate/);assert.equal(await page.locator('[data-widget-aqi]').innerText(),'42');
    assert.equal(await page.locator('.weather-forecast>div').count(),3);
    await page.locator('[data-widget-select=f1]').click();await page.waitForFunction(()=>document.querySelector('[data-widget-race]').textContent==='Canadian Grand Prix');
    assert.match(await page.locator('[data-widget-start]').innerText(),/local time/);assert.equal(await page.locator('[data-race-days]').innerText(),'01');
    for(const [width,height] of [[1280,800],[1280,720],[1024,600],[960,600],[800,1280],[768,1024],[600,960],[412,915],[640,400]]){
      await page.setViewportSize({width,height});
      for(const view of ['weather','f1']){
        await screen('widgets');await page.locator(`[data-widget-select=${view}]`).click();await page.waitForFunction(()=>widgetFeeds[selectedWidget()]?.status==='ready');
        for(const immersive of [false,true]){
          await page.evaluate(enabled=>setPresentation(enabled),immersive);
          for(const phase of ['listening','speaking']){
            voice.phase=phase;await page.evaluate(status=>{voiceState=status;jarvisStatusFreshAt=Date.now();paintJarvisHome()},voice);
            assert.equal(await page.locator('#jarvis-home').isVisible(),phase==='speaking','Only active Jarvis appears on Widgets');
            await layout(`${width}×${height} ${view} immersive=${immersive} ${phase}`);
            await page.evaluate(()=>{const el=document.querySelector('.widget-content');el.scrollTop=el.scrollHeight});
            await layout(`${width}×${height} ${view} scrolled immersive=${immersive} ${phase}`);
            if(((width===1280&&height===800)||(width===412&&height===915)||(width===640&&height===400))&&phase==='speaking'){
              await page.evaluate(()=>{document.querySelector('.widget-content').scrollTop=0;document.querySelector('#toast').hidden=true});
              await page.screenshot({path:path.join(root,`artifacts/widgets-${view}-${immersive?'immersive':'normal'}-jarvis-${width}.png`)});
            }
          }
          await page.evaluate(()=>{document.querySelector('.widget-content').scrollTop=0;setPresentation(false)});
        }
        voice.phase='listening';await page.evaluate(status=>{voiceState=status;paintJarvisHome()},voice);
      }
      for(const face of ['minimal','analog','moon','flip']){
        await screen('clock');await page.locator('[data-clock-face]').selectOption(face);await layout(`${width}×${height} ${face}`);
        if(face==='analog')assert.equal(await page.evaluate(()=>{updateClock(new Date(2026,9,4,3,15,0),false);return document.querySelector('[data-analog-minute]').getAttribute('transform')}),'rotate(90 100 100)');
        if(face==='moon')assert.match(await page.locator('[data-moon-illumination]').innerText(),/approximate/);
      }
    }
    await page.setViewportSize({width:1280,height:800});await screen('clock');await page.locator('[data-clock-face]').selectOption('analog');
    await page.screenshot({path:path.join(root,'artifacts/widgets-analog.png')});
    await page.locator('[data-clock-face]').selectOption('moon');await page.screenshot({path:path.join(root,'artifacts/widgets-moon.png')});
    await screen('widgets');await page.locator('[data-widget-select=weather]').click();await page.waitForFunction(()=>document.querySelector('[data-widget-temperature]').textContent==='14');
    await page.screenshot({path:path.join(root,'artifacts/widgets-weather.png')});
    await page.locator('[data-widget-select=f1]').click();await page.waitForFunction(()=>document.querySelector('[data-widget-race]').textContent==='Canadian Grand Prix');
    await page.screenshot({path:path.join(root,'artifacts/widgets-f1.png')});
    await page.evaluate(()=>setConnection(false,'Reconnecting'));await layout('Widgets reconnecting banner');
    await page.evaluate(()=>setConnection(true,'Live connection'));
    for(const id of ['widgets','clock']){
      await screen(id);await page.locator('[data-screen-focus]').click();
      await page.waitForFunction(()=>presentation&&document.fullscreenElement);
      assert.equal(await page.locator('.surface-dock').isVisible(),false);
      assert.equal(await page.locator('[data-screen-exit]').isVisible(),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1),true,id+' immersive page fits');
      await page.locator('[data-screen-exit]').click();await page.waitForFunction(()=>!presentation);
    }
    await screen('clock');await page.locator('[data-clock-format="12"]').click();
    assert.equal(await page.evaluate(()=>{updateClock(new Date(2026,9,4,0,0,0),false);return document.querySelector('[data-native-period]').textContent}),'AM');
    await screen('widgets');
    await page.reload();await page.waitForFunction(()=>state.paired&&document.body.dataset.view==='widgets');assert.equal(await page.evaluate(()=>widgetPreferences.view),'f1');
    await settings();await page.locator('#widget-settings [name=clock]').selectOption('analog');await page.locator('#widget-settings button[type=submit]').click();
    await page.reload();await page.waitForFunction(()=>state.paired);assert.equal(await page.evaluate(()=>widgetPreferences.clock),'analog');
    await screen('widgets');failures=true;await page.evaluate(()=>refreshWidgets());assert.match(await page.locator('[data-widget-status]').innerText(),/unavailable/);assert.equal(await page.locator('[data-race-days]').innerText(),'—');failures=false;
    // Navigation and hiding abort a pending result before it can repaint the new screen.
    delayed=true;await page.locator('[data-widget-select=weather]').click();while(!releaseWeather)await page.waitForTimeout(20);
    await screen('home');releaseWeather();delayed=false;await page.waitForTimeout(100);assert.equal(await page.locator('.widget-screen').count(),0);
    await screen('widgets');await page.waitForFunction(()=>widgetFeeds.weather?.status==='ready');
    await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});document.dispatchEvent(new Event('visibilitychange'))});
    const count=calls.length;await page.evaluate(()=>refreshWidgets());assert.equal(calls.length,count,'Hidden page makes no feed requests');
    await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'visible'});document.dispatchEvent(new Event('visibilitychange'))});
    assert.equal(await page.evaluate(()=>{showPairing();return document.querySelector('[data-widget-temperature]').textContent}),'—','Losing approval immediately clears displayed feed data');
    await page.reload();
    await page.waitForFunction(()=>state.paired&&!document.querySelector('#pair-dialog').open);
    await settings();await page.locator('#widget-settings [name=clocks]').uncheck();await page.locator('#widget-settings [name=weather]').uncheck();await page.locator('#widget-settings [name=f1]').uncheck();await page.locator('#widget-settings button[type=submit]').click();
    assert.equal(await page.evaluate(()=>document.querySelector('[data-page=widgets]').hidden),true);await screen('clock');assert.equal(await page.locator('.flip-clock').count(),1);
    const offCount=calls.length;await page.evaluate(()=>refreshWidgets());assert.equal(calls.length,offCount);
    await page.evaluate(()=>{location.hash='widgets'});await page.waitForFunction(()=>state.page==='system');
    assert.deepEqual(external,[],'Frontend never requests third-party assets or feeds');assert.deepEqual(errors,[]);
    console.log('Widgets passed: defaults, city selection, preferences, all faces, feeds, failures, late cancellation, visibility, disable/deep links, nine viewports, local assets and CSP.');
  }finally{
    releaseWeather?.();if(!page.isClosed())await page.evaluate(()=>fetch('/api/logout',{method:'POST'})).catch(()=>{});
    await context.close();await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
