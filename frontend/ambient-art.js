// Original deterministic, seamlessly periodic artwork used to render the local video.
function drawEventHorizon(canvas,phase){
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,t=phase*Math.PI*2;
  ctx.fillStyle='#05080f';ctx.fillRect(0,0,w,h);
  const cx=w*.5,cy=h*.48,r=Math.min(w,h)*.22;
  let glow=ctx.createRadialGradient(cx,cy,r*.4,cx,cy,r*2.3);
  glow.addColorStop(0,'#101725');glow.addColorStop(.4,'#16302b');glow.addColorStop(.75,'#071321');glow.addColorStop(1,'#05080f');
  ctx.fillStyle=glow;ctx.fillRect(0,0,w,h);
  for(let i=0;i<170;i++){
    const x=((i*7919)%10000)/10000*w,y=((i*3571)%10000)/10000*h;
    ctx.fillStyle=`rgba(191,222,240,${.12+.24*(1+Math.sin(t+(i%11)))/2})`;
    ctx.fillRect(x,y,i%19===0?2:1,i%19===0?2:1);
  }
  ctx.save();ctx.translate(cx,cy);ctx.rotate(-.32);
  for(let j=24;j>=0;j--){
    ctx.beginPath();ctx.ellipse(0,0,r*(1.24+j*.035),r*(.24+j*.008),0,0,Math.PI*2);
    ctx.strokeStyle=`rgba(${j%2?'121,216,227':'183,244,142'},${.008+(24-j)*.0015})`;ctx.lineWidth=2+(24-j)*.25;ctx.stroke();
  }
  for(let i=0;i<360;i++){
    const a=i/360*Math.PI*2+t,outer=r*(1.4+.09*Math.sin(i*8+t)),x=Math.cos(a)*outer,y=Math.sin(a)*outer*.24;
    ctx.fillStyle=`rgba(${Math.sin(a)>0?'190,250,145':'113,217,237'},${.3+.5*(1+Math.sin(i*2))/2})`;
    ctx.beginPath();ctx.ellipse(x,y,1.2+(i%5)/4,.65,0,0,Math.PI*2);ctx.fill();
  }
  ctx.restore();
  ctx.shadowColor='#b9f788';ctx.shadowBlur=25;ctx.strokeStyle='#bcf890';ctx.lineWidth=2.3;
  ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.stroke();ctx.shadowBlur=0;
  ctx.fillStyle='#03050b';ctx.beginPath();ctx.arc(cx,cy,r*.985,0,Math.PI*2);ctx.fill();
  for(let j=0;j<4;j++){
    ctx.strokeStyle=`rgba(118,219,231,${.08-j*.015})`;ctx.lineWidth=1;ctx.beginPath();ctx.arc(cx,cy,r+8+j*11,0,Math.PI*2);ctx.stroke();
  }
  ctx.save();ctx.translate(cx,cy);ctx.rotate(-.32);
  ctx.beginPath();ctx.ellipse(0,0,r*1.62,r*.32,0,0,Math.PI);ctx.strokeStyle='#d2ffb0';ctx.lineWidth=1.5;ctx.shadowColor='#9bebb9';ctx.shadowBlur=18;ctx.stroke();ctx.restore();
  ctx.strokeStyle='#203641';ctx.lineWidth=1;
  for(const side of [-1,1]){ctx.beginPath();ctx.moveTo(cx+side*r*2.2,cy);ctx.lineTo(cx+side*r*2.6,cy);ctx.stroke()}
}
