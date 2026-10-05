// Trusted fresh QA browser. Chat/model/history are fixtures; never read personal conversations.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1280,height:800},hasTouch:true});
  const page=await context.newPage(),errors=[],writes=[];
  page.on('pageerror',error=>errors.push(error.stack||error.message));
  let rows=[{id:1,heard:'Spoken fixture',reply:'Voice answer',sources:[],action:null}],serial=0,job=null,locked=false,reject=false;
  await page.route('**/api/chat/**',async route=>{
    const request=route.request(),endpoint=new URL(request.url()).pathname.split('/').pop();
    let json;
    if(endpoint==='status')json={ready:!locked,enabled:true,locked,busy:job?.phase==='thinking',turn:job,serverTime:Date.now()};
    else if(endpoint==='history'&&request.method()==='GET')json=rows;
    else if(endpoint==='messages'){
      if(reject){await route.fulfill({status:409,json:{detail:'Fixture busy. Please try again.'}});return}
      writes.push(request.postDataJSON());job={id:String(++serial).padStart(24,'0'),phase:'thinking',message:'Working on your request.'};json={id:job.id};
    }else if(endpoint==='stop'){assert.equal(request.postDataJSON().id,job.id);job.phase='cancelled';job.message='Request stopped.';json={ok:true}}
    else if(endpoint==='history'&&request.method()==='DELETE'){rows=[];job=null;json={ok:true}}
    else throw new Error('Unexpected chat fixture route');
    await route.fulfill({json});
  });
  // Keep voice setup and personal account reads out of this QA profile.
  await page.route('**/api/voice/status',route=>route.fulfill({json:{phase:'off',enabled:false,busy:false,ready:false,history:[],serverTime:Date.now()}}));
  try{
    await page.goto('https://localhost:18761');await page.waitForFunction(()=>state.auth?.local);
    await page.locator('#device-name').fill('Unified chat QA');
    await page.locator('#pair-code').fill(fs.readFileSync(path.join(__dirname,'../.state/private/pairing-code.txt'),'utf8').trim());
    await page.locator('#pair-form button').click();await page.waitForFunction(()=>state.paired&&state.auth?.owner&&state.socket?.readyState===WebSocket.OPEN);
    await page.locator('#more-toggle').click();await page.locator('[data-page="chat"]').click();
    await page.locator('#chat-thread').getByText('Voice answer',{exact:true}).waitFor();
    await page.locator('#chat-input').fill('Typed follow up <img src=x onerror=alert(1)>');
    await page.locator('#chat-input').press('Enter');await page.locator('#chat-stop').waitFor({state:'visible'});
    assert.equal(writes[0].text,'Typed follow up <img src=x onerror=alert(1)>');
    rows.push({id:2,heard:writes[0].text,reply:'Unified reply <script>bad</script>',action:{message:'Calendar checked.'},sources:[{url:'https://example.com/source',title:'Trusted fixture source'},{url:'javascript:bad',title:'Bad link'}]});
    job.phase='done';job.message='Ready.';await page.locator('#chat-thread').getByText('Unified reply <script>bad</script>',{exact:true}).waitFor();
    assert.equal(await page.locator('#chat-thread script,#chat-thread img').count(),0);
    assert.equal(await page.locator('#chat-thread a').count(),1);
    assert.equal(await page.locator('#chat-thread a').getAttribute('rel'),'noopener noreferrer');
    assert.equal(await page.evaluate(()=>[...Object.values(localStorage),...Object.values(sessionStorage)].some(value=>/Typed follow up|Unified reply|Spoken fixture/.test(value))),false);
    await page.reload();await page.waitForFunction(()=>state.paired&&state.page==='chat');await page.locator('#chat-thread').getByText('Voice answer',{exact:true}).waitFor();
    await page.locator('#chat-input').fill('Two lines');await page.locator('#chat-input').press('Shift+Enter');assert.match(await page.locator('#chat-input').inputValue(),/\n/);
    await page.locator('#chat-input').fill('Cancel this');await page.locator('#chat-send').click();await page.locator('#chat-stop').waitFor({state:'visible'});await page.locator('#chat-stop').click();await page.locator('#chat-status').getByText('Request stopped.',{exact:true}).waitFor();
    // Layout and tablet mode (backend tablet authorization is covered separately).
    await page.evaluate(()=>state.auth.owner=false);await page.evaluate(()=>render());assert.equal(await page.locator('#chat-clear').count(),0);
    for(const [width,height] of [[1280,800],[800,1280],[390,844],[1024,600]]){
      await page.setViewportSize({width,height});await page.locator('#chat-thread').getByText('Voice answer',{exact:true}).waitFor();
      const layout=await page.evaluate(()=>{const input=document.querySelector('#chat-input').getBoundingClientRect(),send=document.querySelector('#chat-send').getBoundingClientRect(),dock=document.querySelector('.surface-dock').getBoundingClientRect();return {horizontal:document.documentElement.scrollWidth>innerWidth+1,composerBottom:send.bottom,dockTop:dock.top,inputWidth:input.width,height:innerHeight}});
      assert.equal(layout.horizontal,false,JSON.stringify({width,height,...layout}));
      assert.ok(layout.composerBottom<=layout.dockTop,JSON.stringify({width,height,...layout}));
      assert.ok(layout.inputWidth>=250);
      assert.ok(await page.locator('#chat-send').evaluate(button=>button.getBoundingClientRect().width<180));
    }
    await page.setViewportSize({width:1280,height:800});
    fs.mkdirSync(path.join(__dirname,'../artifacts'),{recursive:true});
    await page.screenshot({path:path.join(__dirname,'../artifacts/chat-qa.png')});
    await page.locator('#chat-input').fill('Show the clock');await page.locator('#chat-send').click();await page.locator('#chat-stop').waitFor({state:'visible'});
    job.phase='done';job.navigation={id:'c'.repeat(24),screen:'clock',expiresAt:Date.now()+10000};
    await page.waitForFunction(()=>state.page==='clock');
    await page.evaluate(()=>goPage('chat'));await page.locator('#chat-thread').getByText('Voice answer',{exact:true}).waitFor();
    await page.reload();await page.waitForFunction(()=>state.paired&&state.page==='chat');await page.locator('#chat-thread').getByText('Voice answer',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>state.page),'chat','Reload does not replay a completed navigation');
    rows.push({id:3,heard:'New spoken follow up',reply:'Shared live voice reply',sources:[],action:null});
    await page.locator('#chat-thread').getByText('Shared live voice reply',{exact:true}).waitFor();
    locked=true;await page.locator('#chat-status').getByText('Unlock the PC to continue the conversation.',{exact:true}).waitFor();assert.equal(await page.locator('[data-chat-row]').count(),0);locked=false;
    await page.locator('#chat-thread').getByText('Voice answer',{exact:true}).waitFor();
    await page.locator('#chat-input').fill('Private draft');await page.locator('[data-page="home"]').click();assert.equal(await page.evaluate(()=>chatRows.length),0);assert.equal(await page.locator('#chat-input').count(),0);
    await page.evaluate(()=>goPage('chat'));await page.locator('#chat-thread').getByText('Voice answer',{exact:true}).waitFor();
    assert.equal(await page.locator('#chat-input').inputValue(),'');
    await page.evaluate(()=>{state.auth.owner=true;render()});await page.locator('#chat-clear').click();await page.locator('#chat-clear').click();await page.waitForFunction(()=>document.querySelectorAll('[data-chat-row]').length===0);
    assert.deepEqual(errors,[]);
    console.log('Unified chat browser checks passed: shared live voice history, typed follow-up, safe sources/text, no message storage, navigation/reload, cancellation, lock, PC/tablet controls, four touch sizes, private draft clearing and shared history deletion. All chat requests mocked.');
  }finally{
    await page.evaluate(async()=>{await fetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'}})}).catch(()=>{});
    await context.close();await browser.close();
  }
})().catch(error=>{console.error(error.stack||String(error));process.exitCode=1});
