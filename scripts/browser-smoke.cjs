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
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error' && /Content Security Policy|Refused/i.test(message.text())) errors.push(message.text()); });
    await page.goto('http://localhost:8000');
    await page.locator('#pair-dialog').waitFor({state:'visible'});
    await page.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/pairing-code.txt'),'utf8').trim());
    await page.locator('#pair-form button').click();
    await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('LIVE CONNECTION'));
    await page.waitForFunction(() => document.querySelector('[data-metric="memory.percent"]').textContent !== '—');
    assert.equal(await page.locator('[data-app]').count(),8);
    assert.equal(await page.evaluate(()=>document.querySelector('#page-content').scrollWidth<=document.querySelector('#page-content').clientWidth),true);
    await page.screenshot({path:path.join(artifacts,'dashboard-landscape.png'),fullPage:true});
    for (const id of ['gaming','hardware','graphs','apps','system','home']) {
      await page.locator(`[data-page="${id}"]`).click();
      assert.equal(await page.locator(`[data-page="${id}"]`).getAttribute('aria-current'),'page');
    }
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
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.screenshot({path:path.join(artifacts,`dashboard-${viewport.width}.png`),fullPage:true});
    }
    await page.locator('[data-page="system"]').click();
    await page.locator('#disconnect').click();
    await page.locator('#pair-dialog').waitFor({state:'visible'});
    assert.equal(await page.evaluate(async()=> (await fetch('/api/apps')).status),401);
    assert.deepEqual(errors,[]);
    console.log('Browser check passed: pairing, live telemetry, six pages, range selection, reconnection, responsive layouts, logout, and CSP.');
    await context.close();
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
