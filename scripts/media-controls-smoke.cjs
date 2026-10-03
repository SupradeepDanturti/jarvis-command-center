// Real browser gestures; mock command dispatch so QA never changes laptop sound.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1280,height:800},hasTouch:true});
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let requests=[],delay=0,fail=false,inflight=0,maxInflight=0,status='paused',stamp=Date.now()+200000;
  try {
    await page.goto(process.env.G16_BASE_URL||'https://localhost:18761');
    await page.waitForFunction(()=>state.auth?.local);
    await page.locator('#device-name').fill('Media controls QA');
    await page.locator('#pair-code').fill(fs.readFileSync(path.join(__dirname,'../.state/private/pairing-code.txt'),'utf8').trim());
    await page.locator('#pair-form button').click();
    await page.waitForFunction(()=>state.paired&&!state.stale);
    const native=await page.evaluate(()=>api('/api/media/state'));
    assert.ok(['playing','paused','stopped','changing','opened','closed','none','unknown'].includes(native.status));
    await page.evaluate(()=>{
      const receive=state.socket.onmessage;
      state.socket.onmessage=event=>{const packet=JSON.parse(event.data);delete packet.media;receive({data:JSON.stringify(packet)})};
    });
    await page.route('**/api/media/*',async route=>{
      const action=route.request().url().split('/').pop();
      if(route.request().method()==='GET')return route.fulfill({json:{status,available:true,sampledAt:++stamp}});
      requests.push(action);inflight++;maxInflight=Math.max(maxInflight,inflight);
      try {
        if(delay)await new Promise(resolve=>setTimeout(resolve,delay));
        if(action==='play-pause')status=status==='playing'?'paused':'playing';
        await route.fulfill(fail?{status:503,json:{detail:'Media test refusal'}}:{json:{ok:true,message:'Checked'}});
      } finally {inflight--}
    });
    const play=()=>page.locator('[data-media="play-pause"]');
    await page.evaluate(stamp=>updateMediaPlayback({status:'paused',sampledAt:stamp}),stamp);
    assert.equal(await play().getAttribute('aria-label'),'Play');
    await play().click();
    await page.waitForFunction(()=>document.querySelector('[data-media="play-pause"]').dataset.playbackIcon==='pause');
    assert.equal(await play().getAttribute('aria-label'),'Pause');
    await play().click();
    await page.waitForFunction(()=>document.querySelector('[data-media="play-pause"]').dataset.playbackIcon==='play');
    assert.deepEqual(requests,['play-pause','play-pause']);
    // An external player change also updates both Home and System.
    await page.evaluate(stamp=>updateMediaPlayback({status:'playing',sampledAt:stamp}),++stamp);
    await page.evaluate(()=>goPage('system'));
    assert.equal(await play().getAttribute('aria-label'),'Pause');
    assert.equal(await play().locator('small').innerText(),'Pause');
    await page.evaluate(stamp=>updateMediaPlayback({status:'none',sampledAt:stamp}),++stamp);
    assert.equal(await play().getAttribute('aria-label'),'Play or pause');
    await page.evaluate(()=>goPage('home'));
    async function down(action='volume-down'){
      const box=await page.locator(`[data-media="${action}"]`).boundingBox();
      await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
    }
    requests=[];
    await page.locator('[data-media="volume-down"]').click();
    await page.waitForTimeout(150);
    assert.deepEqual(requests,['volume-down'],'A tap sends exactly one Windows step');
    requests=[];
    await down();await page.waitForTimeout(250);
    assert.equal(requests.length,1,'Hold has an initial delay');
    await page.waitForTimeout(500);
    assert.ok(requests.length>=3&&requests.length<=8,'Holding repeats volume');
    await page.mouse.up();const released=requests.length;
    await page.waitForTimeout(250);assert.equal(requests.length,released,'Release has no extra click or repeat');
    // Real touch input on the same landscape surface.
    requests=[];
    const cdp=await context.newCDPSession(page);
    const box=await page.locator('[data-media="volume-up"]').boundingBox();
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+box.width/2,y:box.y+box.height/2}]});
    await page.waitForTimeout(650);
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    const touchReleased=requests.length;
    assert.ok(touchReleased>=2&&requests.every(a=>a==='volume-up'));
    await page.waitForTimeout(250);assert.equal(requests.length,touchReleased);
    requests=[];delay=600;maxInflight=0;
    await down();await page.waitForTimeout(100);await page.mouse.up();
    await page.waitForTimeout(800);
    assert.equal(requests.length,1,'Release during a slow request cannot queue later changes');
    assert.equal(maxInflight,1);delay=0;
    for(const stop of [()=>page.evaluate(()=>window.dispatchEvent(new Event('blur'))),
                       ()=>page.evaluate(()=>goPage('system')),
                       ()=>page.evaluate(()=>setConnection(false,'QA DISCONNECT'))]){
      await page.evaluate(()=>goPage('home'));
      await page.waitForFunction(()=>!state.stale);
      requests=[];await down();await page.waitForTimeout(120);await stop();await page.mouse.up();
      const count=requests.length;await page.waitForTimeout(350);assert.equal(requests.length,count);
    }
    await page.waitForFunction(()=>!state.stale);
    await page.evaluate(stamp=>{
      setConnection(false,'QA STALE');
      updateMediaPlayback({status:'playing',sampledAt:stamp});
    },++stamp);
    assert.equal(await play().getAttribute('aria-label'),'Play or pause','Late playback replies cannot restore stale icons');
    await page.waitForFunction(()=>!state.stale);
    requests=[];fail=true;await down();await page.waitForTimeout(650);await page.mouse.up();
    assert.equal(requests.length,1,'Refused command stops repeating');fail=false;
    requests=[];await page.locator('[data-media="volume-up"]').focus();await page.keyboard.press('Enter');
    await page.waitForTimeout(150);assert.deepEqual(requests,['volume-up'],'Keyboard activation remains usable');
    assert.deepEqual(errors,[]);
    console.log('Media checks passed: real playback snapshot, play/pause icons, external state, Home/System, mouse and touch holds, single taps, no queued repeats, blur/navigation/disconnect/refusal, keyboard.');
  } finally {
    await page.unroute('**/api/media/*');
    await page.evaluate(()=>{mediaControls.stop();return fetch('/api/logout',{method:'POST'})}).catch(()=>{});
    await context.close();await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
