// Requires the running HTTPS server and its CA trusted by installed Edge.
const { chromium } = require(process.env.G16_PLAYWRIGHT_PATH || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const ownerContext = await browser.newContext();
  const tabletContext = await browser.newContext();
  try {
    const owner = await ownerContext.newPage();
    const tablet = await tabletContext.newPage();
    const errors = [];
    for(const page of [owner,tablet])page.on('pageerror',e=>errors.push(e.message));
    await owner.goto('https://localhost:18761/#system');
    await owner.waitForFunction(()=>state.auth?.local===true);
    await owner.locator('#device-name').fill('Security check laptop');
    await owner.locator('#pair-code').fill(fs.readFileSync(path.join(root,'.state/private/pairing-code.txt'),'utf8').trim());
    await owner.locator('#pair-form button').click();
    await owner.waitForFunction(()=>document.querySelector('#connection').textContent.includes('LIVE CONNECTION'));
    await tablet.goto(process.env.G16_TABLET_URL || 'https://192.168.2.12:18761');
    await tablet.waitForFunction(()=>state.auth?.local===false);
    assert.equal(await tablet.locator('#setup-code').isVisible(),false);
    await tablet.locator('#device-name').fill('Security check tablet');
    await tablet.locator('#pair-form button').click();
    await tablet.waitForFunction(()=>state.auth?.device?.status==='pending');
    assert.equal(await tablet.evaluate(async()=>(await fetch('/api/apps')).status),401);
    const id = await tablet.evaluate(()=>state.auth.device.id);
    await owner.locator(`[data-approve="${id}"]`).waitFor();
    await owner.locator(`[data-approve="${id}"]`).click();
    await tablet.waitForFunction(()=>document.querySelector('#connection').textContent.includes('LIVE CONNECTION'));
    assert.equal(await tablet.evaluate(async()=>(await fetch('/api/devices')).status),403);
    await tablet.reload();
    await tablet.waitForFunction(()=>document.querySelector('#connection').textContent.includes('LIVE CONNECTION'));
    assert.equal(await tablet.locator('#pair-dialog').isVisible(),false);
    await owner.locator(`[data-revoke="${id}"]`).click();
    await tablet.locator('#pair-dialog').waitFor({state:'visible'});
    assert.equal(await tablet.evaluate(async()=>(await fetch('/api/apps')).status),401);
    assert.deepEqual(errors,[]);
    const ownId = await owner.evaluate(()=>state.auth.device.id);
    await owner.evaluate(async id=>fetch(`/api/devices/${id}/revoke`,{method:'POST'}),ownId);
    console.log('HTTPS security browser check passed: unknown browser denied, fingerprint approval, automatic reconnect, remote management denied, immediate revocation; certificate errors were not bypassed.');
  } finally {await ownerContext.close();await tabletContext.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
