// Deterministic lifecycle checks with controlled browser wake-lock promises.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../frontend/wake.js'),'utf8');
class Lock extends EventTarget{
  released=false;
  async release(){if(this.released)return;this.released=true;this.dispatchEvent(new Event('release'))}
}
function environment({paired=true,enabled=true,supported=true}={}){
  const timers=new Map(),requests=[],locks=[],warnings=[],storage=new Map([['g16-keep-awake',String(enabled)]]);
  const document=new EventTarget();document.visibilityState='visible';document.body={dataset:{}};
  const dialog={open:false};document.querySelector=id=>id==='#pair-dialog'?dialog:null;document.querySelectorAll=()=>[];
  const window=new EventTarget();let timerId=0,behavior=()=>Promise.resolve(new Lock());
  const context=vm.createContext({document,window,state:{paired},isSecureContext:true,Date,Promise,localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},navigator:supported?{wakeLock:{request:type=>{requests.push(type);return behavior().then(lock=>{locks.push(lock);return lock})}}}:{},toast:message=>warnings.push(message),setTimeout:(fn,ms)=>{const id=++timerId;timers.set(id,{fn,ms});return id},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source,context);
  return {context,document,window,requests,locks,timers,warnings,storage,dialog,run:code=>vm.runInContext(code,context),behavior:fn=>behavior=fn,async timer(){const [id,timer]=timers.entries().next().value;timers.delete(id);timer.fn();await drain()}};
}
async function drain(){for(let i=0;i<12;i++)await Promise.resolve()}
(async()=>{
  const normal=environment();
  await normal.run('syncScreenAwake()');assert.equal(normal.document.body.dataset.awake,'active');
  await Promise.all([normal.run('syncScreenAwake()'),normal.run('syncScreenAwake()')]);assert.equal(normal.requests.length,1,'Active lock is reused');
  normal.document.visibilityState='hidden';normal.document.dispatchEvent(new Event('visibilitychange'));await drain();
  assert.equal(normal.locks[0].released,true);assert.equal(normal.timers.size,0);
  normal.document.visibilityState='visible';normal.document.dispatchEvent(new Event('visibilitychange'));await drain();
  assert.equal(normal.requests.length,2);assert.equal(normal.document.body.dataset.awake,'active');
  await normal.locks[1].release();assert.equal(normal.document.body.dataset.awake,'released');assert.equal(normal.timers.size,1);
  await normal.timer();assert.equal(normal.document.body.dataset.awake,'active');
  await normal.run('setKeepAwake(false)');assert.equal(normal.document.body.dataset.awake,'off');assert.equal(normal.storage.get('g16-keep-awake'),'false');
  normal.window.dispatchEvent(new Event('focus'));await drain();assert.equal(normal.requests.length,3,'Off stays off on focus');
  await normal.run('setKeepAwake(true)');normal.context.state.paired=false;await normal.run('syncScreenAwake()');
  assert.equal(normal.locks.at(-1).released,true);assert.equal(normal.document.body.dataset.awake,'waiting');assert.equal(normal.timers.size,0);

  const declined=environment();declined.behavior(()=>Promise.reject(new Error('NotAllowedError')));
  await declined.run('syncScreenAwake()');assert.equal(declined.document.body.dataset.awake,'blocked');assert.equal(declined.timers.size,1);
  assert.equal([...declined.timers.values()][0].ms,2000);await declined.timer();assert.equal([...declined.timers.values()][0].ms,4000);
  for(const delay of [8000,16000,30000,30000]){await declined.timer();assert.equal([...declined.timers.values()][0].ms,delay)}
  assert.equal(declined.warnings.length,1,'Repeated failures do not repeat toasts');
  declined.behavior(()=>Promise.resolve(new Lock()));await declined.run('retryScreenAwake()');assert.equal(declined.document.body.dataset.awake,'active');assert.equal(declined.timers.size,0);

  const delayed=environment();let resolve;
  delayed.behavior(()=>new Promise(done=>resolve=done));
  const first=delayed.run('syncScreenAwake()');await drain();
  const second=delayed.run('syncScreenAwake()');assert.equal(delayed.requests.length,1,'Pending requests are deduplicated');
  await delayed.run('setKeepAwake(false)');const stale=new Lock();resolve(stale);await Promise.all([first,second]);
  assert.equal(stale.released,true,'A late lock must be released after turning off');assert.equal(delayed.document.body.dataset.awake,'off');

  const returning=environment();let finish;
  returning.behavior(()=>new Promise(done=>finish=done));const inFlight=returning.run('syncScreenAwake()');await drain();
  returning.document.visibilityState='hidden';await returning.run('syncScreenAwake()');
  returning.document.visibilityState='visible';returning.run('syncScreenAwake()');
  returning.behavior(()=>Promise.resolve(new Lock()));const old=new Lock();finish(old);await inFlight;await drain();
  assert.equal(old.released,true);assert.equal(returning.requests.length,2);assert.equal(returning.document.body.dataset.awake,'active');

  returning.window.dispatchEvent(new Event('pagehide'));await drain();assert.equal(returning.locks.at(-1).released,true);
  const before=returning.requests.length;returning.window.dispatchEvent(new Event('focus'));await drain();assert.equal(returning.requests.length,before,'Pagehide must suspend requests even before visibility updates');
  returning.window.dispatchEvent(new Event('pageshow'));await drain();assert.equal(returning.document.body.dataset.awake,'active');
  const unsupported=environment({supported:false});await unsupported.run('syncScreenAwake()');assert.equal(unsupported.document.body.dataset.awake,'unsupported');assert.equal(unsupported.timers.size,0);
  const off=environment({enabled:false});await off.run('syncScreenAwake()');assert.equal(off.requests.length,0);assert.equal(off.document.body.dataset.awake,'off');
  const unpaired=environment({paired:false});await unpaired.run('syncScreenAwake()');assert.equal(unpaired.requests.length,0);
  console.log('Wake-lock checks passed: acquisition, reuse, pending races, visibility/OS release, bounded retries, opt-out, page restore, unsupported browsers and unpairing.');
})().catch(error=>{console.error(error);process.exitCode=1});
