// Render original artwork to a local silent WebM loop with installed Edge.
const {chromium}=require(process.env.G16_PLAYWRIGHT_PATH||'playwright');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
  const root=path.resolve(__dirname,'..'),output=path.join(root,'frontend/assets');
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:720}});
    await page.setContent('<canvas width="1280" height="720"></canvas>');
    await page.addScriptTag({path:path.join(root,'frontend/ambient-art.js')});
    for(const [name,draw] of [['event-horizon','drawEventHorizon'],['aurora','drawAurora'],['neon-drift','drawNeonDrift']].filter(([name])=>!process.argv[2]||name===process.argv[2])){
    const result=await page.evaluate(async draw=>{
      const canvas=document.querySelector('canvas'),paint=window[draw];paint(canvas,0);
      const poster=canvas.toDataURL('image/jpeg',.9).split(',')[1];
      const stream=canvas.captureStream(30);
      const mime=['video/webm;codecs=vp9','video/webm;codecs=vp8'].find(type=>MediaRecorder.isTypeSupported(type));
      const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:2800000}),chunks=[];
      recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data)};
      const finished=new Promise(resolve=>recorder.onstop=resolve);
      recorder.start();const started=performance.now();
      await new Promise(resolve=>{function frame(now){const elapsed=(now-started)/1000;paint(canvas,Math.min(elapsed/16,1));if(elapsed>=16){resolve();return}requestAnimationFrame(frame)}requestAnimationFrame(frame)});
      recorder.stop();await finished;stream.getTracks().forEach(track=>track.stop());
      const bytes=new Uint8Array(await new Blob(chunks,{type:mime}).arrayBuffer());
      let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
      return {video:btoa(binary),poster};
    },draw);
    fs.writeFileSync(path.join(output,`${name}.webm`),Buffer.from(result.video,'base64'));
    fs.writeFileSync(path.join(output,`${name}.jpg`),Buffer.from(result.poster,'base64'));
    console.log(`Rendered ${name}: original 1280×720 / 16-second loop and poster.`);
    }
    const nasa=path.join(output,'nasa-black-hole.mp4');
    if(fs.existsSync(nasa)){
      const poster=await page.evaluate(async source=>{
        const video=document.createElement('video');video.muted=true;video.src=source;
        await new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=()=>reject(new Error('NASA movie could not be decoded'))});
        const seeked=new Promise(resolve=>video.onseeked=resolve);video.currentTime=1;await seeked;
        const canvas=document.querySelector('canvas');canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
        return canvas.toDataURL('image/jpeg',.9).split(',')[1];
      },`data:video/mp4;base64,${fs.readFileSync(nasa).toString('base64')}`);
      fs.writeFileSync(path.join(output,'nasa-black-hole.jpg'),Buffer.from(poster,'base64'));
      console.log('Captured a local poster from the unmodified NASA movie.');
    }
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
