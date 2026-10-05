// Render the selected Windows session. No remote artwork or inferred player state.
let mediaDrag = null, mediaPending = null, mediaReceipt = 0;
function homeDeskLinks(){return `<div class="desk-shortcuts"><button data-go="media">Now playing<span data-now-playing-title></span></button><button data-show-focus data-focus-shortcut>Focus timer</button></div>`}
function mediaTime(value){const s=Math.max(0,Math.floor(value||0));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`}
function nowPlayingScreen(){return `<article class="media-surface desk-screen">
  <img id="media-haze" class="media-haze" alt="" aria-hidden="true" hidden><div class="media-wash" aria-hidden="true"></div>
  <div class="media-heading"><span class="surface-overline">JARVIS / NOW PLAYING</span><span class="media-player-badge"><img id="media-player-icon" alt="" hidden><span id="media-player">Your PC</span></span></div>
  <div class="media-composition"><div class="media-art-stage"><div class="media-cover"><img id="media-art" alt="Current album or video artwork" hidden><div id="media-art-fallback" aria-hidden="true">${glyph('play')}</div></div><span class="media-art-caption">YOUR MUSIC, SIR</span></div>
  <div class="media-story"><span id="media-status" class="media-status">AWAITING YOUR SELECTION</span><h2 id="media-title">No player selected, sir</h2><p id="media-artist"></p><p id="media-album" class="reading-detail"></p>
  <div id="media-timeline" hidden><label for="media-seek" class="visually-hidden">Playback position</label><input id="media-seek" type="range" step="1" min="0" max="1" value="0" disabled><div class="media-times"><span id="media-position">0:00</span><span id="media-duration">0:00</span></div></div>
  <div class="session-controls" role="group" aria-label="Current player controls">${[['previous','previous','Previous track'],['play-pause','play','Play or pause'],['next','next','Next track']].map(([id,icon,label])=>`<button data-session-action="${id}" aria-label="${label}" disabled>${glyph(icon)}</button>`).join('')}</div>
  <div class="media-volume" role="group" aria-label="PC volume"><span>PC VOLUME</span><div>${[['volume-down','volume-down','Volume down'],['mute','mute','Mute or unmute'],['volume-up','volume-up','Volume up']].map(([id,icon,label])=>`<button data-media="${id}" aria-label="${label}">${glyph(icon)}</button>`).join('')}</div></div>
  <p id="media-note" class="reading-detail"></p></div></div>
  <div class="media-footer"><button data-desk-pin>Stay on this screen</button>${screenActions()}</div><button class="exit-immersive" data-screen-exit>${glyph('arrow')}<span>Back to display</span></button></article>`}
function cancelMediaInteraction(){mediaDrag=null;mediaPending?.abort();mediaPending=null}
function validMediaArtwork(value){return typeof value==='string'&&/^\/api\/media\/artwork\/[0-9a-f]{24}$/.test(value)}
function paintNowPlaying(){
  const data=state.playback, fresh=deskControlsReady()&&performance.now()-mediaReceipt<5000;
  const available=fresh&&data?.available;
  document.querySelectorAll('[data-now-playing-title]').forEach(el=>el.textContent=available?(data.title||'Track details unavailable'):'Now playing');
  const title=document.querySelector('#media-title');if(!title)return;
  title.textContent=available?(data.title||'Track details unavailable'):'No player selected, sir';
  document.querySelector('#media-artist').textContent=available?(data.artist||''):'';
  document.querySelector('#media-album').textContent=available?(data.album||''):'';
  const player=available?(data.player||'Your PC'):'Your PC',brand=/spotify/i.test(player)?'spotify':/brave/i.test(player)?'brave':null;
  document.querySelector('#media-player').textContent=brand==='spotify'?'Spotify':brand==='brave'?'Brave':player;
  const icon=document.querySelector('#media-player-icon');icon.hidden=!brand;if(brand)icon.src=`/static/assets/icons/${brand}.svg`;else icon.removeAttribute('src');
  document.querySelector('#media-status').textContent=available?data.status==='playing'?'NOW PLAYING':data.status==='paused'?'ON PAUSE':'ON YOUR PC':'AWAITING YOUR SELECTION';
  document.querySelector('.media-surface').classList.toggle('is-playing',!!available&&data.status==='playing');
  const art=document.querySelector('#media-art'),src=available&&validMediaArtwork(data.artwork)?data.artwork:null;
  const haze=document.querySelector('#media-haze');
  if(src){if(art.getAttribute('src')!==src){
    art.onload=()=>{const cover=art.parentElement;cover.style.aspectRatio=String(art.naturalWidth/art.naturalHeight);cover.style.setProperty('--art-limit',`${Math.max(180,Math.min(440,art.naturalWidth*1.5))}px`)};
    art.onerror=()=>{if(!art.isConnected)return;art.hidden=true;haze.hidden=true;document.querySelector('#media-art-fallback').hidden=false};
    art.hidden=false;haze.hidden=false;haze.src=src;art.src=src;
  }}
  else{art.removeAttribute('src');haze.removeAttribute('src');art.hidden=true;haze.hidden=true;art.parentElement.style.aspectRatio='1'}
  document.querySelector('#media-art-fallback').hidden=!!src&&!art.hidden;
  for(const button of document.querySelectorAll('[data-session-action]')){
    button.disabled=!available||!data.trackRevision||!data.controls?.[button.dataset.sessionAction]||!!mediaPending;
    if(button.dataset.sessionAction==='play-pause'){
      const playing=data?.status==='playing';button.setAttribute('aria-label',playing?'Pause':'Play');
      if(button.dataset.icon!==(playing?'pause':'play')){button.innerHTML=glyph(playing?'pause':'play');button.dataset.icon=playing?'pause':'play'}
    }
  }
  const timeline=available?data.timeline:null, slider=document.querySelector('#media-seek');
  document.querySelector('#media-timeline').hidden=!timeline;
  if(mediaDrag&&(mediaDrag.sessionId!==data?.sessionId||mediaDrag.trackRevision!==data?.trackRevision||!fresh))mediaDrag=null;
  if(timeline){
    const elapsed=data.status==='playing'?(performance.now()-mediaReceipt)/1000*(timeline.rate??1):0;
    const position=Math.max(timeline.start,Math.min(timeline.end,timeline.position+elapsed));
    slider.min=timeline.start;slider.max=timeline.end;
    if(!mediaDrag)slider.value=position;
    slider.disabled=!fresh||!data.trackRevision||!data.controls?.seek||!!mediaPending;
    document.querySelector('#media-position').textContent=mediaTime((mediaDrag?Number(slider.value):position)-timeline.start);
    document.querySelector('#media-duration').textContent=mediaTime(timeline.end-timeline.start);
  }
  document.querySelector('#media-note').textContent=!fresh?'Reconnect to see your current player.':!available?'Start music or a video on your PC.':!timeline?'This player has no track timeline.':!data.controls?.seek?'This player does not support seeking.':data.status==='playing'?'Playing on your PC':'Paused or stopped on your PC';
}
function mediaIdentity(){const data=state.playback;return data?.sessionId&&data.trackRevision?{sessionId:data.sessionId,trackRevision:data.trackRevision}:null}
function installNowPlaying(root){
  root.addEventListener('pointerdown',event=>{if(event.target.id==='media-seek'&&!event.target.disabled)mediaDrag=mediaIdentity()});
  root.addEventListener('keydown',event=>{if(event.target.id==='media-seek'&&['ArrowLeft','ArrowRight','Home','End','PageUp','PageDown'].includes(event.key)&&!event.target.disabled)mediaDrag=mediaIdentity()});
  root.addEventListener('input',event=>{if(event.target.id==='media-seek'){mediaDrag??=mediaIdentity();paintNowPlaying()}});
  window.addEventListener('pointercancel',()=>{mediaDrag=null;paintNowPlaying()});
  window.addEventListener('pointerup',()=>setTimeout(()=>{mediaDrag=null;paintNowPlaying()},0));
  root.addEventListener('keyup',event=>{if(event.target.id==='media-seek')setTimeout(()=>{mediaDrag=null;paintNowPlaying()},0)});
  root.addEventListener('change',async event=>{
    if(event.target.id!=='media-seek')return;
    const identity=mediaDrag;mediaDrag=null;
    if(identity&&deskControlsReady()&&!mediaPending)await sendSessionControl('/api/media/seek',{...identity,position:Number(event.target.value)});
  });
  root.addEventListener('click',async event=>{
    const button=event.target.closest('[data-session-action]');if(!button||button.disabled)return;
    const identity=mediaIdentity();if(identity&&deskControlsReady()&&!mediaPending)await sendSessionControl('/api/media/session-action',{...identity,action:button.dataset.sessionAction});
  });
  async function sendSessionControl(url,body){
    const request=new AbortController();mediaPending=request;paintNowPlaying();
    const timeout=setTimeout(()=>request.abort(),8000);
    try{await api(url,{method:'POST',body:JSON.stringify(body),signal:request.signal})}catch(error){if(error.name!=='AbortError')toast(error.message)}
    finally{clearTimeout(timeout);if(mediaPending===request)mediaPending=null;paintNowPlaying()}
  }
}
setInterval(paintNowPlaying,500);
