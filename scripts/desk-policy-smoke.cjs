// Fake clocks verify navigation without changing the laptop or waiting for minutes.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../frontend/display-behavior.js'),'utf8').split('const displayBehavior=')[0];
const sandbox={};vm.runInNewContext(source+';this.policy=createDisplayPolicy;this.normalize=normalizeDisplayPreferences;this.night=nightActive;',sandbox);
let time=0,policy=sandbox.policy(()=>time),context={page:'home',ready:true};
assert.equal(policy.tick(context),null);time=1e7;assert.equal(policy.tick(context),null,'Defaults never navigate');
assert.equal(sandbox.normalize({dwell:-1,pages:['evil'],night:true,start:'25:00'}).start,'22:00');
let widgetTime=0,widgetPolicy=sandbox.policy(()=>widgetTime);
widgetPolicy.configure({rotation:true,dwell:30,pages:['home','widgets','clock']});
widgetPolicy.tick({page:'home',ready:true,widgetsEnabled:false});widgetTime=30000;
assert.equal(widgetPolicy.tick({page:'home',ready:true,widgetsEnabled:false}),'clock','Disabled widgets are skipped');
widgetPolicy=sandbox.policy(()=>widgetTime);widgetPolicy.configure({rotation:true,dwell:30,pages:['home','widgets']});
widgetPolicy.tick({page:'home',ready:true,widgetsEnabled:true});widgetTime+=30000;
assert.equal(widgetPolicy.tick({page:'home',ready:true,widgetsEnabled:true}),'widgets','Enabled widgets can rotate');
const prefs={night:true,start:'22:00',end:'07:00'};
for(const [hour,minute,dim] of [[21,59,false],[22,0,true],[0,0,true],[6,59,true],[7,0,false]])assert.equal(sandbox.night(prefs,new Date(2026,9,3,hour,minute)),dim);
assert.equal(sandbox.night({...prefs,end:'22:00'},new Date(2026,9,3,23)),false);
time=0;policy=sandbox.policy(()=>time);policy.configure({rotation:true,dwell:30,pages:['home','clock']});
policy.tick(context);time=30000;assert.equal(policy.tick(context),'clock');context.page='clock';
policy.manual('clock');time+=120000;assert.equal(policy.tick(context),null);time+=30000;assert.equal(policy.tick(context),'home');
policy.togglePin();time+=1e6;assert.equal(policy.tick(context),null);policy.togglePin();policy.tick(context);time+=30000;assert.equal(policy.tick(context),'home');
for(const blocker of ['interacting','menu','presentation','focus']){
 context[blocker]=true;time+=1e6;assert.equal(policy.tick(context),null,blocker);context[blocker]=false;
 assert.equal(policy.tick(context),null);time+=29999;assert.equal(policy.tick(context),null);time++;assert.equal(policy.tick(context),'home');
}
time=0;policy=sandbox.policy(()=>time);policy.configure({media:true,games:true});context={page:'home',ready:true,playing:true,sessionId:'player'};
policy.tick(context);time=4999;assert.equal(policy.tick(context),null);time=5000;assert.equal(policy.tick(context),'media');context.page='media';
time+=10000;assert.equal(policy.tick(context),null,'Unchanged playback enters once');
context.game={id:'game'};policy.tick(context);time+=5000;assert.equal(policy.tick(context),'gaming');context.page='gaming';
policy.manual('home');context.page='home';time+=120000;policy.tick(context);time+=10000;assert.equal(policy.tick(context),null,'Manual choice cannot be stolen by unchanged activity');
context.game=null;policy.tick(context);time+=5000;assert.equal(policy.tick(context),'media');context.page='media';
context.playing=false;policy.tick(context);time+=9999;assert.equal(policy.tick(context),null);time++;assert.equal(policy.tick(context),'home');
context.ready=false;context.playing=true;time+=1e6;assert.equal(policy.tick(context),null);context.ready=true;policy.tick(context);time+=4999;assert.equal(policy.tick(context),null);time++;assert.equal(policy.tick(context),'media');
policy.configure({});time+=1e6;assert.equal(policy.tick(context),null,'Disabling cancels navigation');
console.log('Display policy passed: defaults, schedule boundaries, invalid settings, rotation, manual hold, pin, interaction blockers, media/game priority, exit and reconnect.');
