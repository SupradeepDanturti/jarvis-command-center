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
    assert.equal(await page.evaluate(()=>document.querySelector('#page-content').scrollWidth<=document.querySelector('#page-content').clientWidth),true);
    await page.screenshot({path:path.join(artifacts,'dashboard-landscape.png'),fullPage:true});
    for (const id of ['gaming','games','hardware','graphs','apps','clock','ambient','system','devices','home']) {
      await page.locator(`[data-page="${id}"]`).click();
      assert.equal(await page.locator(`[data-page="${id}"]`).getAttribute('aria-current'),'page');
    }
    await page.locator('[data-page="apps"]').click();
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
    await page.locator('[data-page="clock"]').click();
    assert.match(await page.locator('[data-clock-hours]').innerText(),/^\d{2}$/);
    await page.locator('[data-clock-format="12"]').click();
    assert.match(await page.locator('[data-clock-period]').innerText(),/AM|PM/);
    await page.locator('[data-clock-format="24"]').click();
    await page.locator('[data-screen-focus]').click();
    assert.equal(await page.locator('body').evaluate(body=>body.classList.contains('presentation')),true);
    await page.screenshot({path:path.join(artifacts,'clock-immersive.png')});
    await page.locator('[data-screen-exit]').click();
    assert.equal(await page.locator('body').evaluate(body=>body.classList.contains('presentation')),false);
    await page.locator('[data-page="ambient"]').click();
    await page.waitForFunction(()=>document.querySelector('#ambient-video').currentTime>.3);
    assert.equal(await page.evaluate(()=>new Promise(resolve=>{const video=document.querySelector('#ambient-video');let previous=video.currentTime;const deadline=Date.now()+25000;const timer=setInterval(()=>{const current=video.currentTime;if(current<previous-.5){clearInterval(timer);resolve(true)}else if(Date.now()>deadline){clearInterval(timer);resolve(false)}previous=current},200)})),true,'Ambient video must loop');
    await page.screenshot({path:path.join(artifacts,'ambient-landscape.png'),fullPage:true});
    await page.locator('[data-motion-toggle]').click();
    assert.equal(await page.locator('#ambient-video').evaluate(video=>video.paused),true);
    for(const scene of ['grid','aurora','horizon']){
      await page.locator(`[data-scene-select="${scene}"]`).click();
      assert.equal(await page.locator('.ambient-screen').getAttribute('data-scene'),scene);
    }
    await page.locator('[data-motion-toggle]').click();
    await page.locator('[data-page="games"]').click();
    await page.waitForFunction(()=>state.gameLibrary!==null);
    const gameCount=await page.locator('[data-game]').count();
    assert.equal(gameCount,await page.evaluate(()=>state.games.length));
    if(gameCount){
      await page.locator('#game-search').fill('no game matches this search 99999');
      assert.equal(await page.locator('[data-game]').count(),0);
      await page.locator('#game-search').fill('');
      assert.equal(await page.locator('[data-game]').count(),gameCount);
    }
    await page.screenshot({path:path.join(artifacts,'games-landscape.png'),fullPage:true});
    await page.locator('[data-page="home"]').click();
    await page.locator('[data-range="300"]').click();
    assert.equal(await page.locator('[data-range="300"]').getAttribute('class'),'active');
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
        await page.locator(`[data-page="${id}"]`).click();
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${id} overflows at ${viewport.width}`);
      }
      await page.locator('[data-page="home"]').click();
      await page.screenshot({path:path.join(artifacts,`dashboard-${viewport.width}.png`),fullPage:true});
    }
    await page.locator('[data-page="system"]').click();
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
