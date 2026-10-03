// Original stylized black-hole artwork, rendered offline to a seamless local loop.
// The tablet plays the video; this renderer never runs on the tablet.
const horizonBackgrounds=new WeakMap();
function horizonBackground(canvas){
  if(horizonBackgrounds.has(canvas))return horizonBackgrounds.get(canvas);
  const layer=document.createElement('canvas');layer.width=canvas.width;layer.height=canvas.height;
  const ctx=layer.getContext('2d'),w=layer.width,h=layer.height;
  ctx.fillStyle='#03050c';ctx.fillRect(0,0,w,h);
  for(const [x,y,r,color] of [[.24,.28,.52,'#183447'],[.79,.4,.42,'#40201b'],[.7,.8,.45,'#131b38']]){
    const fog=ctx.createRadialGradient(w*x,h*y,0,w*x,h*y,w*r);
    fog.addColorStop(0,color);fog.addColorStop(1,'#03050c00');ctx.fillStyle=fog;ctx.fillRect(0,0,w,h);
  }
  let seed=731;
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296};
  for(let i=0;i<550;i++){
    const x=random()*w,y=h*(.12+.5*x/w)+(random()-.5)*h*.3,r=8+random()*35;
    const dust=ctx.createRadialGradient(x,y,0,x,y,r);
    dust.addColorStop(0,`rgba(70,95,133,${.012+random()*.025})`);dust.addColorStop(1,'#0000');
    ctx.fillStyle=dust;ctx.fillRect(x-r,y-r,r*2,r*2);
  }
  for(let i=0;i<1100;i++){
    const x=random()*w,y=random()*h,bright=random(),size=bright>.98?2:bright>.8?1.2:.6;
    ctx.fillStyle=`rgba(${i%4===0?'255,210,157':'193,218,255'},${.15+bright*.65})`;
    ctx.fillRect(x,y,size,size);
    if(bright>.988){ctx.strokeStyle='#b8d8ff45';ctx.lineWidth=.5;ctx.beginPath();ctx.moveTo(x-4,y);ctx.lineTo(x+4,y);ctx.moveTo(x,y-4);ctx.lineTo(x,y+4);ctx.stroke()}
  }
  horizonBackgrounds.set(canvas,layer);return layer;
}
function drawEventHorizon(canvas,phase){
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,t=phase*Math.PI*2;
  ctx.drawImage(horizonBackground(canvas),0,0);
  const cx=w*.55+Math.sin(t)*3,cy=h*.43+Math.cos(t)*2,r=Math.min(w,h)*.175;
  const corona=ctx.createRadialGradient(cx,cy,r*.75,cx,cy,r*3.5);
  corona.addColorStop(0,'#ef8f3b24');corona.addColorStop(.3,'#ffbe6538');corona.addColorStop(.65,'#a1461910');corona.addColorStop(1,'#0000');
  ctx.fillStyle=corona;ctx.fillRect(0,0,w,h);
  ctx.save();ctx.translate(cx,cy);ctx.rotate(-.09);
  function disk(front){
    ctx.globalCompositeOperation='screen';
    for(let j=74;j>=0;j--){
      const q=j/74,rad=r*(1.13+q*2.15),hot=1-q;
      const shimmer=.75+.25*Math.sin(j*.7+t*2);
      ctx.strokeStyle=`rgba(255,${Math.round(105+hot*119)},${Math.round(42+hot*121)},${(.02+hot*.27)*shimmer})`;
      ctx.lineWidth=1.5+hot*2.8;ctx.beginPath();ctx.ellipse(0,0,rad,rad*.205,0,front?0:Math.PI,front?Math.PI:Math.PI*2);ctx.stroke();
    }
    for(let i=0;i<1150;i++){
      const q=((i*3571)%10000)/10000,rad=r*(1.17+q*2.05),a=i*2.399963+t*(q<.35?2:1);
      if((Math.sin(a)>0)!==front)continue;
      const glow=(1-q)*(.25+.5*(1+Math.sin(i*3.1+t*2))/2);
      ctx.fillStyle=`rgba(255,${Math.round(140+(1-q)*102)},${Math.round(64+(1-q)*132)},${glow})`;
      ctx.fillRect(Math.cos(a)*rad,Math.sin(a)*rad*.205,1.4+(1-q)*2,.6+(1-q)*.8);
    }
    ctx.globalCompositeOperation='source-over';
  }
  disk(false);
  // Stylized bent-back disk above the shadow; this is artwork, not a physics simulation.
  ctx.globalCompositeOperation='screen';
  for(let j=24;j>=0;j--){
    const q=j/24;
    ctx.strokeStyle=`rgba(255,${Math.round(155+(1-q)*80)},${Math.round(80+(1-q)*116)},${.055+(1-q)*.17})`;
    ctx.lineWidth=2.5;ctx.beginPath();ctx.ellipse(0,0,r*(1.04+q*.33),r*(1.04+q*.3),0,Math.PI,Math.PI*2);ctx.stroke();
  }
  ctx.globalCompositeOperation='source-over';
  ctx.shadowColor='#ffb854';ctx.shadowBlur=25;ctx.strokeStyle='#ffe2ad';ctx.lineWidth=2.2;
  ctx.beginPath();ctx.arc(0,0,r,0,Math.PI*2);ctx.stroke();ctx.shadowBlur=0;
  ctx.fillStyle='#010207';ctx.beginPath();ctx.arc(0,0,r*.988,0,Math.PI*2);ctx.fill();
  disk(true);
  ctx.globalCompositeOperation='screen';ctx.strokeStyle='#ffdeb18a';ctx.lineWidth=1.2;
  ctx.beginPath();ctx.ellipse(0,0,r*2.8,r*.08,0,0,Math.PI);ctx.stroke();ctx.restore();
  const vignette=ctx.createRadialGradient(w*.5,h*.45,h*.3,w*.5,h*.45,w*.65);
  vignette.addColorStop(0,'#0000');vignette.addColorStop(1,'#010208a0');ctx.fillStyle=vignette;ctx.fillRect(0,0,w,h);
}

function drawAurora(canvas,phase){
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,t=phase*Math.PI*2;
  ctx.drawImage(horizonBackground(canvas),0,0);
  ctx.fillStyle='#00121880';ctx.fillRect(0,0,w,h);
  const glow=ctx.createRadialGradient(w*.55,h*.3,0,w*.55,h*.3,w*.65);
  glow.addColorStop(0,'#0b6b5a55');glow.addColorStop(.5,'#24355a30');glow.addColorStop(1,'#0000');
  ctx.fillStyle=glow;ctx.fillRect(0,0,w,h);
  ctx.save();ctx.globalCompositeOperation='screen';
  // Fine vertical veils bend together into broad, luminous curtains.
  for(let layer=0;layer<5;layer++){
    const colors=['70,255,176','57,219,232','125,111,255','73,237,176','133,212,255'];
    const crest=[];
    for(let i=0;i<=210;i++){
      const u=i/210,x=u*w;
      const y=h*(.18+layer*.045+.065*Math.sin(u*7+t+layer*.8)+.055*Math.sin(u*13-t+layer));
      const length=h*(.14+.1*(1+Math.sin(u*9+t*2+layer))/2);
      const alpha=(.12+.08*Math.sin(u*25+layer)**2)*Math.sin(u*Math.PI);
      const ribbon=ctx.createLinearGradient(x,y,x,y+length);
      ribbon.addColorStop(0,'#0000');ribbon.addColorStop(.06,`rgba(${colors[layer]},${alpha*2})`);
      ribbon.addColorStop(.22,`rgba(${colors[layer]},${alpha})`);ribbon.addColorStop(1,'#0000');
      ctx.fillStyle=ribbon;ctx.fillRect(x,y,w/210+1,length);crest.push([x,y]);
    }
    ctx.strokeStyle=`rgba(${colors[layer]},.07)`;ctx.lineWidth=14;ctx.shadowColor=`rgb(${colors[layer]})`;ctx.shadowBlur=35;
    ctx.beginPath();crest.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.stroke();ctx.shadowBlur=0;
  }
  ctx.restore();
  // Snow ridges and a quiet lake anchor the light to a landscape.
  for(let layer=0;layer<3;layer++){
    ctx.fillStyle=['#152935','#0b1b28','#06131d'][layer];ctx.beginPath();ctx.moveTo(0,h);
    for(let i=0;i<=48;i++){
      const x=i*w/48,y=h*(.64+layer*.06-.085*Math.sin(i*.67+layer)-.035*Math.sin(i*2.1+layer));
      ctx.lineTo(x,y);
    }
    ctx.lineTo(w,h);ctx.closePath();ctx.fill();
  }
  const lake=ctx.createLinearGradient(0,h*.78,0,h);lake.addColorStop(0,'#173c4055');lake.addColorStop(1,'#020b14');
  ctx.fillStyle=lake;ctx.fillRect(0,h*.8,w,h*.2);
  for(let i=0;i<28;i++){
    const y=h*(.81+i*.006),spread=w*(.02+i*.011);
    ctx.strokeStyle=`rgba(110,214,191,${.065*(1-i/28)})`;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(w*.52-spread+Math.sin(t+i)*5,y);ctx.lineTo(w*.52+spread+Math.sin(t+i)*5,y);ctx.stroke();
  }
}

function drawNeonDrift(canvas,phase){
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,t=phase*Math.PI*2,vanish=h*.49;
  const sky=ctx.createLinearGradient(0,0,0,h);sky.addColorStop(0,'#030517');sky.addColorStop(.5,'#23103b');sky.addColorStop(1,'#060c20');
  ctx.fillStyle=sky;ctx.fillRect(0,0,w,h);
  ctx.globalAlpha=.45;ctx.drawImage(horizonBackground(canvas),0,0);ctx.globalAlpha=1;
  const haze=ctx.createRadialGradient(w*.52,vanish,0,w*.52,vanish,w*.65);
  haze.addColorStop(0,'#d3459455');haze.addColorStop(.35,'#743db530');haze.addColorStop(1,'#0000');ctx.fillStyle=haze;ctx.fillRect(0,0,w,h);
  const radius=h*.19,cx=w*.52,cy=h*.34;
  const sun=ctx.createLinearGradient(0,cy-radius,0,cy+radius);sun.addColorStop(0,'#ffd6a9');sun.addColorStop(.45,'#f575b8');sun.addColorStop(1,'#8a38bd');
  ctx.save();ctx.beginPath();ctx.arc(cx,cy,radius,0,Math.PI*2);ctx.clip();ctx.fillStyle=sun;
  for(let i=0;i<34;i++){const y=cy-radius+i*radius*2/34;ctx.fillRect(cx-radius,y,radius*2,radius*2/34*(i<14?1:.55))}ctx.restore();
  for(let side=0;side<2;side++){
    ctx.beginPath();ctx.moveTo(side?w:0,h);
    for(let i=0;i<=18;i++){
      const x=side?w-i*w*.026:i*w*.026,y=vanish-h*(.025+.15*Math.abs(Math.sin(i*1.73+side)))*(1-i/22);
      ctx.lineTo(x,y);
    }
    ctx.lineTo(w*.5,vanish);ctx.lineTo(side?w:0,h);ctx.closePath();ctx.fillStyle='#090d25';ctx.fill();
    ctx.strokeStyle=side?'#ea59c766':'#4bdcfb66';ctx.lineWidth=1.5;ctx.stroke();
  }
  const floor=ctx.createLinearGradient(0,vanish,0,h);floor.addColorStop(0,'#101228');floor.addColorStop(1,'#030918');
  ctx.fillStyle=floor;ctx.fillRect(0,vanish,w,h-vanish);
  ctx.save();ctx.shadowBlur=10;ctx.shadowColor='#52cfff';ctx.lineWidth=1;
  for(let i=-15;i<=15;i++){
    ctx.strokeStyle=i%3===0?'#73d8fa88':'#5367c544';ctx.beginPath();ctx.moveTo(w*.5+i*3,vanish);ctx.lineTo(w*.5+i*w*.12,h);ctx.stroke();
  }
  for(let i=0;i<24;i++){
    const depth=((i+phase*4)%24)/24,y=vanish+depth**3*(h-vanish);
    ctx.strokeStyle=`rgba(129,113,239,${.1+depth*.45})`;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();
  }
  // Light rails and traffic streaks converge on the horizon.
  for(const side of [-1,1]){
    ctx.strokeStyle=side<0?'#68e8ff':'#f768d3';ctx.shadowColor=ctx.strokeStyle;ctx.lineWidth=3;
    ctx.beginPath();ctx.moveTo(w*.5+side*12,vanish);ctx.lineTo(w*.5+side*w*.3,h);ctx.stroke();
    for(let i=0;i<22;i++){
      const depth=(i/22+phase*2)%1,fade=Math.sin(depth*Math.PI)**2;
      const y=vanish+depth**3*(h-vanish),x=w*.5+side*(12+depth**3*w*.35);
      ctx.globalAlpha=fade*.75;ctx.lineWidth=1+depth*3;
      ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+side*depth**2*13,y+depth**2*28);ctx.stroke();
    }
    ctx.globalAlpha=1;
  }
  ctx.restore();
  const vignette=ctx.createRadialGradient(w*.5,h*.4,h*.15,w*.5,h*.4,w*.65);
  vignette.addColorStop(0,'#0000');vignette.addColorStop(1,'#02061790');ctx.fillStyle=vignette;ctx.fillRect(0,0,w,h);
}
