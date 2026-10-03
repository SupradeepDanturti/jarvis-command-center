// Touch viewport checks against the running, trusted local server.
const { chromium } = require(process.env.G16_PLAYWRIGHT_PATH || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const artifacts = path.join(root, 'artifacts');
  fs.mkdirSync(artifacts, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, hasTouch: true, deviceScaleFactor: 2 });
  const page = await context.newPage();
  const reportOnly = process.argv.includes('--report');
  const issues = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  async function screen(id) {
    await page.evaluate(id => { location.hash = id; }, id);
    await page.waitForFunction(id => document.body.dataset.view === id, id);
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  function check(ok, message) { if (!ok) issues.push(message); }
  try {
    await page.goto(process.env.G16_BASE_URL || 'https://localhost:18761');
    await page.waitForFunction(() => state.auth?.local === true);
    await page.locator('#device-name').fill('Tablet layout check');
    await page.locator('#pair-code').fill(fs.readFileSync(path.join(root, '.state/private/pairing-code.txt'), 'utf8').trim());
    await page.locator('#pair-form button').click();
    await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('LIVE CONNECTION'));
    async function waitForReport(width, height, mode) {
      await page.waitForFunction(async ({ width, height, mode }) => {
        const devices = await (await fetch('/api/devices')).json();
        const report = devices.find(device => device.id === state.auth.device.id)?.display;
        return report?.width === width && report?.height === height && (!mode || report.mode === mode);
      }, { width, height, mode }, { polling: 200 });
    }
    for (const [width, height] of [[1280,800],[1280,720],[1024,600],[960,600],[800,1280],[768,1024],[600,960],[412,915],[640,400]]) {
      await page.setViewportSize({ width, height });
      await waitForReport(width, height, 'Normal browser');
      for (const entry of ['home','gaming','apps','games','clock','ambient','ambient:grid','ambient:aurora','ambient:blackhole']) {
        const [id,variant]=entry.split(':');
        await screen(id);
        if(id==='ambient')await page.locator(`[data-scene-select="${variant||'horizon'}"]`).click();
        if (id === 'games') await page.waitForFunction(() => state.gameLibrary !== null);
        // Exercise wide numerals even when the current CPU load/time is narrow.
        if (id === 'clock') await page.evaluate(() => updateClock(new Date(2026,9,3,23,58,0),false));
        const layout = await page.evaluate(() => {
          const dock = document.querySelector('.surface-dock').getBoundingClientRect();
          const content = document.querySelector('#page-content').getBoundingClientRect();
          const targets = [...document.querySelectorAll('#page-content button, .clock-digits, .clock-dial, .ambient-caption, .ambient-live-clock, .hero-reading')];
          const overlap = targets.filter(el => {
            const r = el.getBoundingClientRect();
            return r.width && r.height && r.top < dock.bottom && r.bottom > dock.top && r.right > dock.left && r.left < dock.right;
          }).map(el => el.className || el.getAttribute('data-app') || el.textContent.trim());
          const outside = targets.filter(el => {
            const r = el.getBoundingClientRect();
            return r.width && r.height && (r.left < -1 || r.right > innerWidth + 1);
          }).map(el => el.className || el.textContent.trim());
          const scene = document.querySelector('.desk-screen');
          let largeReadingFits = true;
          let readingInsideCircle = true;
          let readingProportion = 0;
          let circleCrossers = [];
          const hero = document.querySelector('.hero-reading');
          if (hero) {
            const metric = hero.querySelector('[data-metric]');
            const current = metric.textContent;
            metric.textContent = '100';
            const halo = document.querySelector('.core-halo').getBoundingClientRect();
            largeReadingFits = hero.getBoundingClientRect().width <= halo.width - 8;
            const centerX = halo.left + halo.width / 2;
            const centerY = halo.top + halo.height / 2;
            const radius = halo.width / 2 - 6;
            circleCrossers = [...document.querySelectorAll('.core-reading > :not(.core-halo)')].filter(el => {
              const r = el.getBoundingClientRect();
              return [[r.left,r.top],[r.right,r.top],[r.left,r.bottom],[r.right,r.bottom]]
                .some(([x,y]) => Math.hypot(x-centerX,y-centerY) > radius);
            }).map(el => el.className);
            readingInsideCircle = circleCrossers.length === 0;
            readingProportion = parseFloat(getComputedStyle(hero).fontSize) / halo.width;
            metric.textContent = current;
          }
          return {
            overflow: document.documentElement.scrollWidth > innerWidth + 1,
            overlap, outside, largeReadingFits, readingInsideCircle, readingProportion, circleCrossers,
            fits: content.bottom <= dock.top - 8,
            sceneHeight: scene?.getBoundingClientRect().height,
            dockLabel: parseFloat(getComputedStyle(document.querySelector('.surface-dock small')).fontSize),
            appLabel: document.querySelector('.app-name') ? parseFloat(getComputedStyle(document.querySelector('.app-name')).fontSize) : null,
          };
        });
        const label = `${width}×${height} ${entry}`;
        check(!layout.overflow, `${label}: page overflow`);
        check(layout.largeReadingFits, `${label}: 100% reading does not fit inside the halo`);
        check(layout.readingInsideCircle, `${label}: ${layout.circleCrossers.join(', ')} crosses the circle`);
        check(layout.readingProportion <= .36, `${label}: processor reading is too large relative to circle`);
        if (height >= 600 || ['clock','ambient'].includes(id)) check(!layout.overlap.length, `${label}: dock covers ${layout.overlap.join(', ')}`);
        if (id !== 'games') check(!layout.outside.length, `${label}: content clipped ${layout.outside.join(', ')}`);
        check(layout.dockLabel >= 10, `${label}: dock labels too small (${layout.dockLabel}px)`);
        if (width >= 600 && height >= 600 && ['home','gaming','apps','games'].includes(id)) check(layout.fits, `${label}: composition needs vertical scrolling`);
        if (layout.sceneHeight) check(Math.abs(layout.sceneHeight - height) <= 1, `${label}: scene exceeds visible height`);
        if (layout.appLabel) check(layout.appLabel >= 11, `${label}: app labels too small (${layout.appLabel}px)`);
        // In short phone windows, scrolling must expose the final control above the dock.
        if (height < 600 && !['clock','ambient'].includes(id)) {
          const last = page.locator('#page-content button:enabled').last();
          if (await last.count()) {
            await last.evaluate(el => el.scrollIntoView({ block: 'center', inline: 'center' }));
            check(await last.evaluate(el => el.getBoundingClientRect().bottom < document.querySelector('.surface-dock').getBoundingClientRect().top), `${label}: last control cannot be scrolled clear of dock`);
            await page.evaluate(() => window.scrollTo(0, 0));
          }
        }
        if ([[1280,800],[1024,600],[800,1280]].some(([w,h]) => w === width && h === height)) {
          await page.screenshot({ path: path.join(artifacts, `tablet-${reportOnly ? 'before' : 'after'}-${width}-${entry.replace(':','-')}.png`), fullPage: true, animations: 'disabled' });
        }
      }
    }
    // Immersive scenes still fit when rotating into a short landscape window.
    await page.setViewportSize({ width: 960, height: 600 });
    await screen('clock');
    await page.locator('[data-screen-focus]').click();
    await page.setViewportSize({ width: 600, height: 960 });
    await waitForReport(600, 960, 'Fullscreen');
    check(await page.locator('.desk-screen').evaluate(el => el.getBoundingClientRect().height === innerHeight), 'Immersive portrait height');
    await page.locator('[data-screen-exit]').click();
    check(await page.locator('.surface-dock').isVisible(), 'Dock restored after immersive view');
    await waitForReport(600, 960, 'Normal browser');
    await screen('system');
    assert.equal(await page.locator('#display-size').innerText(), '600 × 960');
    await page.evaluate(() => { navigator.clipboard.writeText = async text => { window.copiedDisplayDetails = text; }; });
    await page.locator('#copy-display-details').click();
    await page.waitForFunction(() => window.copiedDisplayDetails?.includes('600 × 960 CSS px'));
    assert.match(await page.evaluate(() => window.copiedDisplayDetails), /Mode: Portrait · Normal browser/);
    console.log(JSON.stringify({ issues, errors }, null, 2));
    if (!reportOnly) { assert.deepEqual(issues, []); assert.deepEqual(errors, []); }
  } finally {
    // Revoke only this test browser, preserving the user's approvals.
    const logout = await page.evaluate(async () => (await fetch('/api/logout', { method: 'POST' })).status).catch(() => null);
    await context.close();
    await browser.close();
    assert.equal(logout, 200, 'The QA browser credential must be revoked');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
