// Optional local browser check. Install Playwright or set G16_PLAYWRIGHT_PATH.
const { chromium } = require(process.env.G16_PLAYWRIGHT_PATH || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const artifacts = path.join(root, 'artifacts');
  fs.mkdirSync(artifacts, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  let context,page;
  try {
    context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    page = await context.newPage();
    async function screen(id){const button=page.locator(`[data-page="${id}"]`);if(!await button.isVisible())await page.locator('#more-toggle').click();await button.click()}
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error' && /Content Security Policy|Refused/i.test(message.text())) errors.push(message.text()); });
    await page.goto(process.env.G16_BASE_URL || 'https://localhost:18761');
    await page.locator('#pair-dialog').waitFor({state:'visible'});
    await page.waitForFunction(() => state.auth?.local === true);
    await page.locator('#device-name').fill('Browser smoke check');
    await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());
    await page.locator('#pair-form button').click();
    await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('LIVE CONNECTION'));
    await page.waitForFunction(() => document.querySelector('[data-metric="memory.percent"]').textContent !== '—');
    assert.equal(await page.locator('[data-app]').count(),8);
    assert.equal(await page.locator('.sidebar').count(),0);
    assert.equal(await page.locator('#page-content .card').count(),0);
    assert.equal(await page.locator('.core-halo').count(),0);
    assert.equal(await page.locator('.orbit-cpu').count(),1);
    assert.equal(await page.locator('#surface-background').getAttribute('data-scene'),'blackhole');
    assert.match(await page.locator('.orbit-credit').innerText(),/NASA.*Jeremy Schnittman/);
    // Verify registered media dispatch without altering the user's real sound.
    const mediaRequests=[];
    await page.route('**/api/media/*',async route=>{mediaRequests.push(route.request().url().split('/').pop());assert.equal(route.request().method(),'POST');await route.fulfill({json:{ok:true,message:'Sound control checked'}})});
    for(const id of ['volume-down','mute','volume-up']){
      const button=page.locator(`.orbit-controls [data-media="${id}"]`);
      assert.equal(await button.isVisible(),true);
      await button.click();
    }
    assert.deepEqual(mediaRequests,['volume-down','mute','volume-up']);
    await page.unroute('**/api/media/*');
    assert.equal(await page.locator('.surface-dock').isVisible(),true);
    assert.equal(await page.locator('#page-content').evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight-100),true,'Home composition must fit above the dock');
    assert.equal(await page.evaluate(()=>document.querySelector('#page-content').scrollWidth<=document.querySelector('#page-content').clientWidth),true);
    await page.screenshot({path:path.join(artifacts,'dashboard-landscape.png'),fullPage:true});
    for (const id of ['gaming','games','hardware','graphs','apps','clock','ambient','system','devices','home']) {
      await screen(id);
      assert.equal(await page.locator(`[data-page="${id}"]`).getAttribute('aria-current'),'page');
      assert.equal(await page.locator('#surface-background').count(),1,'Navigation must reuse a single background player');
      if(id==='ambient'){
        assert.equal(await page.locator('.surface-backdrop').isVisible(),false);
        assert.equal(await page.locator('#surface-background').evaluate(video=>video.paused),true);
      }else{
        const expected={gaming:'grid',games:'blackhole',hardware:'horizon',graphs:'grid',apps:'aurora',clock:'horizon',system:'aurora',devices:'aurora',home:'blackhole'};
        assert.equal(await page.locator('#surface-background').getAttribute('data-scene'),expected[id]);
        await page.waitForFunction(()=>document.querySelector('#surface-background').currentTime>.1);
        assert.equal(await page.locator('.surface-backdrop').evaluate(el=>getComputedStyle(el).pointerEvents==='none'&&Number(getComputedStyle(el).zIndex)<0),true,'Backdrop must stay behind touch controls');
        assert.equal(await page.locator('#surface-background').evaluate(v=>v.muted&&v.loop&&v.playsInline),true);
      }
    }
    await screen('system');
    await page.locator('#background-scene').selectOption('grid');
    await screen('home');
    assert.equal(await page.locator('#surface-background').getAttribute('data-scene'),'blackhole','Home keeps its requested NASA scene');
    await screen('apps');
    assert.equal(await page.locator('#surface-background').getAttribute('data-scene'),'grid','Other screens honor the background choice');
    await screen('system');
    await page.locator('#background-scene').selectOption('blackhole');
    await page.locator('#background-motion').click();
    await page.reload();
    await page.waitForFunction(()=>state.paired&&document.querySelector('#background-scene'));
    assert.equal(await page.locator('#background-scene').inputValue(),'blackhole');
    await screen('home');
    assert.equal(await page.locator('#surface-background').getAttribute('data-scene'),'blackhole');
    assert.equal(await page.locator('#surface-background').evaluate(v=>v.paused),true,'Background pause survives reload and navigation');
    await screen('system');
    await page.locator('#background-motion').click();
    await page.locator('#background-scene').selectOption('auto');
    await screen('home');
    await page.waitForFunction(()=>!document.querySelector('#surface-background').paused);
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.waitForFunction(()=>document.querySelector('#surface-background').paused);
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.waitForFunction(()=>!document.querySelector('#surface-background').paused);
    await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});document.dispatchEvent(new Event('visibilitychange'))});
    assert.equal(await page.locator('#surface-background').evaluate(v=>v.paused),true,'Hidden pages pause backgrounds');
    await page.evaluate(()=>{delete document.visibilityState;document.dispatchEvent(new Event('visibilitychange'))});
    await page.waitForFunction(()=>!document.querySelector('#surface-background').paused);
    await page.evaluate(()=>{for(const id of ['apps','home','gaming','hardware','home'])goPage(id)});
    await page.waitForFunction(()=>document.querySelector('#surface-background').currentTime>.1);
    await page.screenshot({path:path.join(artifacts,'moving-background-home.png'),fullPage:true});
    await screen('apps');
    for(const id of ['steam','discord','brave','youtube']){
      assert.equal(await page.locator(`[data-app="${id}"] img`).count(),1);
      assert.equal(await page.locator(`[data-app="${id}"] img`).evaluate(img=>img.complete&&img.naturalWidth>0),true);
    }
    assert.equal(await page.locator('[data-app="youtube"] .app-status').innerText(),'Open in Brave');
    let launchBody;
    await page.route('**/api/apps/launch',async route=>{launchBody=route.request().postDataJSON();await route.fulfill({json:{ok:true,message:'Shortcut checked'}})});
    await page.locator('[data-app="youtube"]').click();
    await page.waitForFunction(()=>document.querySelector('#toast').textContent==='Shortcut checked');
    assert.deepEqual(launchBody,{id:'youtube'});
    await page.unroute('**/api/apps/launch');
    await page.screenshot({path:path.join(artifacts,'applications-landscape.png'),fullPage:true});
    await screen('clock');
    assert.equal(await page.locator('.clock-screen').evaluate(el=>el.getBoundingClientRect().width===innerWidth),true);
    assert.match(await page.locator('[data-clock-hours]').innerText(),/^\d{2}$/);
    assert.equal(await page.locator('.flip-tile').count(),2);
    assert.equal(await page.locator('.clock-dial').count(),0);
    const rollover=await page.evaluate(()=>{updateClock(new Date(2026,9,3,23,59,59),false);updateClock(new Date(2026,9,4,0,0,0));return {values:[...document.querySelectorAll('.flip-tile')].map(tile=>tile.dataset.value),flipping:document.querySelectorAll('.flip-tile.flipping').length}});
    assert.deepEqual(rollover,{values:['00','00'],flipping:2});
    await page.waitForFunction(()=>!document.querySelector('.flip-tile.flipping'));
    assert.equal(await page.locator('.flip-tile').evaluateAll(tiles=>tiles.every(tile=>[...tile.querySelectorAll('.flip-top .flip-numeral,.flip-bottom .flip-numeral')].every(face=>face.textContent===tile.dataset.value))),true);
    await page.locator('[data-clock-format="12"]').click();
    assert.match(await page.locator('[data-clock-period]').innerText(),/AM|PM/);
    const midnight=await page.evaluate(()=>{updateClock(new Date(2026,9,4,0,0,0),false);return {hours:document.querySelector('[data-clock-hours]').textContent,period:document.querySelector('[data-clock-period]').textContent}});
    assert.deepEqual(midnight,{hours:'12',period:'AM'});
    assert.equal(await page.evaluate(()=>{updateClock(new Date(2026,9,4,12,0,0),false);return document.querySelector('[data-clock-period]').textContent}),'PM');
    await page.emulateMedia({reducedMotion:'reduce'});
    const reducedFlip=await page.evaluate(()=>{updateClock(new Date(2026,9,4,12,0,0),false);updateClock(new Date(2026,9,4,12,1,0));return {flipping:document.querySelectorAll('.flip-tile.flipping').length,minutes:document.querySelector('.flip-tile[data-flip-unit="minutes"] .flip-bottom .flip-numeral').textContent}});
    assert.deepEqual(reducedFlip,{flipping:0,minutes:'01'});
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.locator('[data-clock-format="24"]').click();
    await page.locator('[data-screen-focus]').click();
    assert.equal(await page.locator('body').evaluate(body=>body.classList.contains('presentation')),true);
    await page.screenshot({path:path.join(artifacts,'clock-immersive.png')});
    await page.locator('[data-screen-exit]').click();
    assert.equal(await page.locator('body').evaluate(body=>body.classList.contains('presentation')),false);
    await screen('ambient');
    assert.equal(await page.locator('.ambient-screen').evaluate(el=>el.getBoundingClientRect().width===innerWidth),true);
    await page.locator('[data-motion-toggle]').click();
    assert.equal(await page.locator('#ambient-video').evaluate(video=>video.paused),true);
    for(const scene of ['grid','aurora','blackhole','horizon']){
      await page.locator(`[data-scene-select="${scene}"]`).click();
      assert.equal(await page.locator('.ambient-screen').getAttribute('data-scene'),scene);
      assert.equal(await page.locator('#ambient-video').evaluate(video=>video.paused),true,'Changing scenes must preserve pause');
      await page.waitForFunction(()=>{const v=document.querySelector('#ambient-video');return v.readyState>=3&&v.networkState===1&&v.buffered.length});
      assert.equal(await page.locator('#ambient-video').evaluate(video=>video.videoWidth>0&&video.videoHeight>0),true);
      assert.equal(await page.locator('#ambient-video').evaluate(video=>getComputedStyle(video).display!=='none'),true);
      assert.equal(await page.locator('#ambient-video').evaluate(video=>video.muted&&video.loop&&video.playsInline),true);
      assert.equal(await page.evaluate(()=>new Promise(resolve=>{const img=new Image();img.onload=()=>resolve(img.naturalWidth>0);img.onerror=()=>resolve(false);img.src=document.querySelector('#ambient-video').poster})),true,'Every scene needs a local still poster');
      if(scene==='blackhole')assert.match(await page.locator('#scene-credit').innerText(),/NASA.*Jeremy Schnittman/);
      await page.locator('[data-motion-toggle]').click();
      await page.waitForFunction(()=>document.querySelector('#ambient-video').currentTime>.3);
      // Observe a real loop boundary without waiting through each entire movie.
      await page.evaluate(()=>new Promise(resolve=>{const v=document.querySelector('#ambient-video');const end=Number.isFinite(v.duration)?v.duration:v.buffered.end(v.buffered.length-1);v.addEventListener('seeked',resolve,{once:true});v.currentTime=Math.max(.3,end-.7)}));
      assert.equal(await page.evaluate(()=>new Promise(resolve=>{const video=document.querySelector('#ambient-video');let previous=video.currentTime;const deadline=Date.now()+6000;const timer=setInterval(()=>{const current=video.currentTime;if(current<previous-.5){clearInterval(timer);resolve(true)}else if(Date.now()>deadline){clearInterval(timer);resolve(false)}previous=current},100)})),true,`${scene} movie must loop`);
      await page.screenshot({path:path.join(artifacts,`ambient-${scene}-landscape.png`),fullPage:true});
      await page.locator('[data-motion-toggle]').click();
    }
    await page.locator('[data-scene-select="blackhole"]').click();
    await page.reload();
    await page.waitForFunction(()=>state.auth?.device?.status==='approved'&&document.querySelector('.ambient-screen')?.dataset.scene==='blackhole');
    assert.equal(await page.locator('#ambient-video').evaluate(video=>video.paused),true,'Scene and pause preference survive reload');
    await page.locator('[data-motion-toggle]').click();
    await page.evaluate(()=>{for(const scene of ['grid','aurora','blackhole','horizon','grid']){screenPreferences.scene=scene;updateAmbient()}});
    await page.waitForFunction(()=>document.querySelector('#ambient-video').currentTime>.3);
    assert.equal(await page.locator('.ambient-screen').getAttribute('data-motion'),'true','Rapid switching must not leave playback paused');
    await screen('games');
    await page.waitForFunction(()=>state.gameLibrary!==null);
    const gameCount=await page.locator('[data-game]').count();
    assert.equal(gameCount,await page.evaluate(()=>state.games.length));
    await page.locator('#games-list').evaluate(el=>{for(const [type,x] of [['touchstart',320],['touchend',80]]){const event=new Event(type,{bubbles:true});Object.defineProperty(event,'changedTouches',{value:[{clientX:x,clientY:200}]});el.dispatchEvent(event)}});
    assert.equal(await page.evaluate(()=>state.page),'games','Swiping the poster rail must not change screens');
    if(gameCount){
      await page.locator('#game-search').fill('no game matches this search 99999');
      assert.equal(await page.locator('[data-game]').count(),0);
      await page.locator('#game-search').fill('');
      assert.equal(await page.locator('[data-game]').count(),gameCount);
    }
    await page.screenshot({path:path.join(artifacts,'games-landscape.png'),fullPage:true});
    await screen('graphs');
    await page.locator('[data-range="300"]').first().click();
    assert.equal(await page.locator('[data-range="300"]').first().getAttribute('class'),'active');
    await context.setOffline(true);
    // Chromium offline emulation does not reliably drop an existing WebSocket.
    await page.evaluate(() => state.socket.close());
    await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('RECONNECTING'));
    assert.equal(await page.locator('#offline-banner').isVisible(),true);
    await context.setOffline(false);
    await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('LIVE CONNECTION'),{},{timeout:20000});
    for(const viewport of [{width:800,height:1280},{width:412,height:915}]) {
      await page.setViewportSize(viewport);
      for(const id of ['home','apps','clock','ambient','games','devices']){
        await screen(id);
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${id} overflows at ${viewport.width}`);
      }
      await screen('home');
      await page.screenshot({path:path.join(artifacts,`dashboard-${viewport.width}.png`),fullPage:true});
    }
    await screen('system');
    await page.locator('#disconnect').click();
    await page.locator('#pair-dialog').waitFor({state:'visible'});
    assert.equal(await page.evaluate(async()=> (await fetch('/api/apps')).status),401);
    assert.deepEqual(errors,[]);
    const reducedContext=await browser.newContext({reducedMotion:'reduce'});
    const reducedPage=await reducedContext.newPage();
    await reducedPage.goto('https://localhost:18761/#ambient');
    await reducedPage.locator('#pair-dialog').waitFor({state:'visible'});
    assert.equal(await reducedPage.locator('.ambient-screen').getAttribute('data-motion'),'false');
    assert.equal(await reducedPage.locator('#ambient-video').evaluate(video=>video.paused),true);
    await reducedContext.close();
    console.log('Browser check passed: ten pages, local logos, YouTube shortcut, clock/immersive view, ambient video/scenes, game library/search, telemetry, responsive layouts, reconnect, logout, and CSP.');
    await context.close();
  } finally {
    if(page&&!page.isClosed())await page.evaluate(()=>fetch('/api/logout',{method:'POST'})).catch(()=>{});
    if(context)await context.close();
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
