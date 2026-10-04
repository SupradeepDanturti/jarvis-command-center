// Original native compositions; only approved, same-origin data requests.
const clockFaces={flip:'Flip',minimal:'Minimal',analog:'Analog',moon:'Moon phase'};
function normalizeWidgetPreferences(value){
  const prefs={clocks:false,clock:'flip',weather:false,f1:false,location:null,view:'weather'};
  if(!value||typeof value!=='object')return prefs;
  for(const key of ['clocks','weather','f1'])if(typeof value[key]==='boolean')prefs[key]=value[key];
  if(Object.hasOwn(clockFaces,value.clock))prefs.clock=value.clock;
  if(['weather','f1'].includes(value.view))prefs.view=value.view;
  const place=value.location;
  if(place&&typeof place.name==='string'&&place.name.length<=160&&Number.isFinite(place.latitude)&&Math.abs(place.latitude)<=90&&Number.isFinite(place.longitude)&&Math.abs(place.longitude)<=180){
    prefs.location={name:place.name,latitude:Math.round(place.latitude*1000)/1000,longitude:Math.round(place.longitude*1000)/1000};
  }
  return prefs;
}
let widgetPreferences=normalizeWidgetPreferences(null);
try{widgetPreferences=normalizeWidgetPreferences(JSON.parse(localStorage.getItem('g16-widget-preferences')||'{}'))}catch{}
let widgetLocations=[],widgetSearchGeneration=0,widgetSearchAbort;
let widgetAbort,widgetTimer,widgetGeneration=0,widgetFeeds={},widgetReceipt=0,widgetServerTime=0;
function widgetsEnabled(){return widgetPreferences.weather||widgetPreferences.f1}
function saveWidgetPreferences(){try{localStorage.setItem('g16-widget-preferences',JSON.stringify(widgetPreferences))}catch{}}
function widgetSettings(){
  const prefs=widgetPreferences;
  return `<section class="desk-settings widget-settings"><h3>Optional widgets</h3><form id="widget-settings"><label class="setting-check"><input name="clocks" type="checkbox" ${prefs.clocks?'checked':''}>Extra clock faces</label><label>Clock face<select name="clock">${Object.entries(clockFaces).map(([id,name])=>`<option value="${id}" ${prefs.clock===id?'selected':''}>${name}</option>`).join('')}</select></label><p class="section-note">Minimal, analog and approximate moon phase work offline. Enable extra faces to use them on Clock.</p><label class="setting-check"><input name="weather" type="checkbox" ${prefs.weather?'checked':''}>Weather & air quality</label><p data-widget-city class="section-note">${prefs.location?`Selected city: <strong>${escapeHtml(prefs.location.name)}</strong>`:'Choose a city below to show weather.'} Conditions and modelled air quality come from Open-Meteo; your selected city coordinates are sent to that service when viewed. Its free service is for personal, non-commercial use.</p><label class="setting-check"><input name="f1" type="checkbox" ${prefs.f1?'checked':''}>F1 next race</label><p class="section-note">Race schedule and countdown from Jolpica. Live race timing is unavailable.</p><button type="submit">Save optional widgets</button></form><form id="widget-location-search"><label>Find a city<input name="query" type="search" minlength="2" maxlength="80" placeholder="City, country" required autocomplete="off"></label><button type="submit">Find city</button></form><p id="widget-search-status" class="section-note" role="status"></p><div id="widget-location-results" class="widget-location-results"></div><p class="section-note">Choices are saved on this browser. Open enabled screens from More → Widgets. Add Widgets in Display behavior to include the selected widget in slow rotation.</p></section>`;
}
function clockFacePicker(){return widgetPreferences.clocks?`<label class="clock-face-picker">Clock face<select data-clock-face>${Object.entries(clockFaces).map(([id,name])=>`<option value="${id}" ${widgetPreferences.clock===id?'selected':''}>${name}</option>`).join('')}</select></label>`:''}
function nativeClockScreen(){
  const face=widgetPreferences.clock;
  const ticks=Array.from({length:12},(_,i)=>`<line x1="100" y1="13" x2="100" y2="${i%3===0?25:19}" transform="rotate(${i*30} 100 100)"/>`).join('');
  const analog=`<svg class="analog-face" viewBox="0 0 200 200" role="img" aria-label="Analog clock"><circle class="analog-rim" cx="100" cy="100" r="94"/><g class="analog-ticks">${ticks}</g><g data-analog-hour><line class="analog-hour" x1="100" y1="100" x2="100" y2="52"/></g><g data-analog-minute><line class="analog-minute" x1="100" y1="100" x2="100" y2="32"/></g><g data-analog-second><line class="analog-second" x1="100" y1="112" x2="100" y2="28"/></g><circle class="analog-center" cx="100" cy="100" r="3"/></svg>`;
  const moon=`<div class="moon-composition"><svg class="moon-face" viewBox="0 0 100 100" role="img" aria-label="Approximate moon phase"><circle class="moon-dark" cx="50" cy="50" r="40"/><path class="moon-light" data-moon-half/><ellipse data-moon-ellipse cx="50" cy="50" ry="40"/></svg><div><span class="surface-overline">APPROXIMATE MOON PHASE</span><h2 data-moon-label></h2><p data-moon-illumination></p><p class="section-note">Calculated cycle estimate</p></div></div>`;
  const digits=`<div class="native-digits" role="timer" aria-live="off"><span data-clock-hours>00</span><span aria-hidden="true">:</span><span data-clock-minutes>00</span><small data-native-period></small></div>`;
  return `<article class="desk-screen clock-screen native-clock ${face}-clock"><div class="screen-kicker"><span>JARVIS / ${clockFaces[face].toUpperCase()} CLOCK</span><span data-clock-zone></span></div><div class="native-clock-center">${face==='analog'?analog:face==='moon'?moon:''}${digits}<span data-clock-date></span></div><div class="screen-bottom"><div class="native-clock-options"><div class="segmented"><button data-clock-format="24" class="${screenPreferences.format==='24'?'active':''}">24 H</button><button data-clock-format="12" class="${screenPreferences.format==='12'?'active':''}">12 H</button><button data-clock-mode="focus">Focus timer</button><button data-go="rest">Rest & alarms</button></div>${clockFacePicker()}</div>${screenActions()}</div><button class="exit-immersive" data-screen-exit>${glyph('arrow')}<span>Back to display</span></button></article>`;
}
function paintNativeClock(now=new Date()){
  if(!document.querySelector('.native-clock'))return;
  const seconds=now.getSeconds(),minutes=now.getMinutes()+seconds/60,hours=now.getHours()%12+minutes/60;
  const period=document.querySelector('[data-native-period]');if(period)period.textContent=screenPreferences.format==='12'?(now.getHours()<12?'AM':'PM'):'';
  for(const [name,angle] of [['hour',hours*30],['minute',minutes*6],['second',seconds*6]])document.querySelector(`[data-analog-${name}]`)?.setAttribute('transform',`rotate(${angle} 100 100)`);
  const analog=document.querySelector('.analog-face');if(analog)analog.setAttribute('aria-label',`Local time ${now.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`);
  // Mean cycle anchored to NASA's 2000-01-06 18:14 UT new moon; not an ephemeris.
  // https://eclipse.gsfc.nasa.gov/phase/phases1901.html
  const phase=((now.getTime()-Date.UTC(2000,0,6,18,14))/(29.530588*86400000)%1+1)%1;
  const curve=Math.cos(2*Math.PI*phase),waxing=phase<.5;
  document.querySelector('[data-moon-half]')?.setAttribute('d',`M50 10 A40 40 0 0 ${waxing?1:0} 50 90 Z`);
  const ellipse=document.querySelector('[data-moon-ellipse]');if(ellipse){ellipse.setAttribute('rx',String(Math.abs(curve)*40));ellipse.setAttribute('class',curve>=0?'moon-dark':'moon-light')}
  const labels=['New moon','Waxing crescent','First quarter','Waxing gibbous','Full moon','Waning gibbous','Last quarter','Waning crescent'];
  const label=labels[Math.round(phase*8)%8];
  const moonLabel=document.querySelector('[data-moon-label]');if(moonLabel)moonLabel.textContent=label;
  const illumination=document.querySelector('[data-moon-illumination]');if(illumination)illumination.textContent=`${Math.round((1-curve)*50)}% illuminated · approximate`;
}
function selectedWidget(){return widgetPreferences[widgetPreferences.view]?widgetPreferences.view:widgetPreferences.weather?'weather':'f1'}
function widgetScreen(){
  const view=selectedWidget();
  const tabs=[['weather','Weather & air'],['f1','Next race']].filter(([id])=>widgetPreferences[id]);
  const main=view==='weather'?`<div class="weather-composition"><div class="weather-main"><span class="surface-overline">${escapeHtml(widgetPreferences.location?.name||'CHOOSE A CITY')}</span><h2 class="weather-temperature"><span data-widget-temperature>—</span><em>°C</em></h2><p class="weather-condition" data-widget-condition>Conditions unavailable</p><div class="weather-details"><span data-widget-feels></span><span data-widget-wind></span><span data-widget-humidity></span></div></div><div class="weather-air"><span class="surface-overline">US AIR QUALITY INDEX</span><strong data-widget-aqi>—</strong><p>Model estimate · CAMS</p><p data-widget-particles></p><p data-widget-air-status class="section-note"></p></div><div class="weather-forecast" data-widget-forecast></div></div>`:`<div class="race-composition"><span class="surface-overline">NEXT SCHEDULED GRAND PRIX</span><h2 data-widget-race>Race schedule unavailable</h2><p data-widget-circuit></p><div class="race-countdown" role="timer" aria-live="off">${['Days','Hours','Minutes','Seconds'].map(unit=>`<div><strong data-race-${unit.toLowerCase()}>—</strong><span>${unit}</span></div>`).join('')}</div><p data-widget-start></p><p data-widget-qualifying class="section-note"></p><p class="section-note">Schedule countdown · live race timing unavailable</p></div>`;
  return `<article class="desk-screen widget-screen" data-widget-view="${view}"><div class="screen-kicker"><span>JARVIS / ${view==='weather'?'OUTSIDE':'RACE WEEKEND'}</span><div class="widget-header-actions"><button data-go="system">Widget settings</button><button class="exit-immersive" data-screen-exit>${glyph('arrow')}<span>Back to display</span></button></div></div><div class="widget-voice-slot"></div><div class="widget-content" tabindex="0" role="region" aria-label="Widget readings">${main}<p data-widget-status class="widget-feed-status" role="status">${view==='weather'&&!widgetPreferences.location?'Choose a city in Optional widgets.':'Checking the latest update…'}</p><div class="widget-source">${view==='weather'?'<a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a> · <a href="https://atmosphere.copernicus.eu/" target="_blank" rel="noopener noreferrer">CAMS</a> · Location: GeoNames':'<a href="https://jolpi.ca/" target="_blank" rel="noopener noreferrer">Jolpica F1</a>'}</div></div><div class="screen-bottom"><div class="segmented">${tabs.map(([id,label])=>`<button data-widget-select="${id}" class="${view===id?'active':''}">${label}</button>`).join('')}</div>${screenActions()}</div></article>`;
}
function stopWidgets(clear=false){clearTimeout(widgetTimer);widgetAbort?.abort();widgetAbort=null;widgetGeneration++;if(clear){widgetFeeds={};widgetServerTime=0;widgetReceipt=0;paintWidgets()}widgetSearchAbort?.abort();widgetSearchGeneration++}
function widgetsActive(){return state.paired&&state.page==='widgets'&&widgetsEnabled()&&document.visibilityState==='visible'&&!restState?.rest}
function mountWidgets(){
  stopWidgets();
  const menu=document.querySelector('[data-page="widgets"]');if(menu)menu.hidden=!widgetsEnabled();
  if(!widgetsActive())return;
  paintWidgets();refreshWidgets();
}
async function refreshWidgets(){
  if(!widgetsActive())return;
  const generation=widgetGeneration,view=selectedWidget(),place=widgetPreferences.location;
  if(view==='weather'&&!place)return;
  widgetAbort=new AbortController();
  const cancelled=widgetAbort.signal,signal=AbortSignal.any([cancelled,AbortSignal.timeout(12000)]);
  const read=async(kind)=>{
    try{
      const options=kind==='f1'?{signal}:{method:'POST',signal,body:JSON.stringify({latitude:place.latitude,longitude:place.longitude})};
      const result=await api(`/api/widgets/${kind}`,options);
      if(generation!==widgetGeneration||!widgetsActive())return;
      widgetFeeds[kind]={...result,receivedAt:performance.now()};
      if(kind==='f1'){widgetServerTime=result.serverTime;widgetReceipt=performance.now()}
    }catch(error){
      if(generation!==widgetGeneration||cancelled.aborted)return;
      widgetFeeds[kind]={...widgetFeeds[kind],status:'stale'};
    }
  };
  await Promise.all(view==='weather'?[read('weather'),read('air-quality')]:[read('f1')]);
  if(generation!==widgetGeneration||!widgetsActive())return;
  paintWidgets();widgetTimer=setTimeout(refreshWidgets,60000);
}
function widgetValue(value,digits=0){return Number.isFinite(value)?value.toLocaleString([],{maximumFractionDigits:digits}):'—'}
function widgetDate(seconds,options,timezone){if(!Number.isFinite(seconds))return '—';try{return new Date(seconds*1000).toLocaleString([],{...options,...(timezone?{timeZone:timezone}:{})})}catch{return new Date(seconds*1000).toLocaleString([],options)}}
function feedData(kind){const feed=widgetFeeds[kind],maxAge=kind==='weather'?3600:kind==='air-quality'?7200:86400;const age=feed?feed.serverTime-feed.fetchedAt+(performance.now()-feed.receivedAt)/1000:Infinity;return feed?.fetchedAt&&age>=0&&age<=maxAge?feed.data:null}
function weatherDescription(code){if(code==null)return 'Conditions unavailable';if(code===0)return 'Clear skies';if(code<=3)return 'Cloud cover';if([45,48].includes(code))return 'Fog';if(code>=51&&code<=57)return 'Drizzle';if(code>=61&&code<=67)return 'Rain';if(code>=71&&code<=77)return 'Snow';if(code>=80&&code<=82)return 'Rain showers';if([85,86].includes(code))return 'Snow showers';if(code>=95)return 'Thunderstorms';return 'Conditions unavailable'}
function paintWidgets(){
  if(!document.querySelector('.widget-screen'))return;
  const set=(name,value)=>{const el=document.querySelector(`[data-widget-${name}]`);if(el)el.textContent=value};
  const view=selectedWidget(),feed=widgetFeeds[view],data=feedData(view);
  if(view==='weather'){
    const air=feedData('air-quality');
    set('temperature',widgetValue(data?.temperature,1));set('condition',weatherDescription(data?.code));
    set('feels',`Feels like ${widgetValue(data?.feelsLike,1)}°C`);set('wind',`Wind ${widgetValue(data?.wind)} km/h`);set('humidity',`Humidity ${widgetValue(data?.humidity)}%`);
    set('aqi',widgetValue(air?.aqi));set('particles',`PM2.5 ${widgetValue(air?.pm25,1)} · PM10 ${widgetValue(air?.pm10,1)} µg/m³`);
    set('air-status',air?`Model time ${widgetDate(air.observedAt,{hour:'2-digit',minute:'2-digit'},data?.timezone)}${widgetFeeds['air-quality']?.status==='stale'?' · Cached; update unavailable':''}`:'Air quality unavailable');
    const forecast=document.querySelector('[data-widget-forecast]');
    forecast.replaceChildren();
    for(const day of data?.days||[]){const item=document.createElement('div');const title=document.createElement('span');title.textContent=widgetDate(day.time,{weekday:'short'},data.timezone);const reading=document.createElement('strong');reading.textContent=`${widgetValue(day.high)}° / ${widgetValue(day.low)}°`;const rain=document.createElement('small');rain.textContent=`Rain ${widgetValue(day.rain)}%`;item.append(title,reading,rain);forecast.append(item)}
    if(data?.days?.[0]){const day=data.days[0],sun=document.createElement('p');sun.className='weather-sun';sun.textContent=`Sunrise ${widgetDate(day.sunrise,{hour:'2-digit',minute:'2-digit'},data.timezone)} · Sunset ${widgetDate(day.sunset,{hour:'2-digit',minute:'2-digit'},data.timezone)}`;forecast.append(sun)}
  }else{
    const race=data?.race;
    set('race',race?.name||(data?'No upcoming race in this season':'Race schedule unavailable'));
    set('circuit',race?[race.circuit,race.location].filter(Boolean).join(' · '):'');
    set('start',race?`${widgetDate(race.start,{weekday:'long',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'})} · your local time`:'');
    set('qualifying',race?.qualifying?`Qualifying · ${widgetDate(race.qualifying,{weekday:'short',hour:'2-digit',minute:'2-digit',timeZoneName:'short'})}`:'');
    paintRaceCountdown();
  }
  set('status',!feed?'Checking the latest update…':!data?'Feed unavailable. Try again when connected.':`${feed.status==='stale'?'Cached · update unavailable · ':'Updated '}${widgetDate(feed.fetchedAt,{hour:'2-digit',minute:'2-digit'})}${view==='weather'?` · Conditions ${widgetDate(data.observedAt,{hour:'2-digit',minute:'2-digit'},data.timezone)}`:''}`);
  if(view==='weather'&&!widgetPreferences.location)set('status','Choose a city in Optional widgets.');
}
function paintRaceCountdown(){
  if(!document.querySelector('.race-countdown'))return;
  const race=feedData('f1')?.race,serverNow=widgetServerTime+(performance.now()-widgetReceipt)/1000;
  let remaining=race?Math.max(0,Math.floor(race.start-serverNow)):null;
  for(const [unit,size] of [['days',86400],['hours',3600],['minutes',60],['seconds',1]]){const el=document.querySelector(`[data-race-${unit}]`);el.textContent=remaining===null?'—':String(Math.floor(remaining/size)).padStart(2,'0');if(remaining!==null)remaining%=size}
  if(race&&race.start<=serverNow){const status=document.querySelector('[data-widget-status]');if(status)status.textContent='Scheduled start reached · live race timing unavailable';}
}
function installWidgets(root){
  root.addEventListener('change',event=>{if(!event.target.matches('[data-clock-face]'))return;widgetPreferences.clock=event.target.value;saveWidgetPreferences();render()});
  root.addEventListener('click',event=>{
    const view=event.target.closest('[data-widget-select]'),choice=event.target.closest('[data-widget-location]');
    if(view&&widgetPreferences[view.dataset.widgetSelect]){widgetPreferences.view=view.dataset.widgetSelect;saveWidgetPreferences();render();scrollTo(0,0)}
    if(choice){const place=widgetLocations[Number(choice.dataset.widgetLocation)];if(!place)return;widgetPreferences.location=place;widgetFeeds={};saveWidgetPreferences();const label=document.querySelector('[data-widget-city]');label.textContent=`Selected city: ${place.name}. Your selected city coordinates are sent to Open-Meteo when viewed; its free service is for personal, non-commercial use.`;document.querySelector('#widget-location-results').replaceChildren();document.querySelector('#widget-search-status').textContent='City saved.';toast('City saved, sir.')}
  });
  root.addEventListener('submit',async event=>{
    if(event.target.id==='widget-settings'){
      event.preventDefault();const form=new FormData(event.target);
      widgetPreferences={...widgetPreferences,clocks:form.has('clocks'),clock:form.get('clock'),weather:form.has('weather'),f1:form.has('f1')};
      if(!widgetPreferences.weather){delete widgetFeeds.weather;delete widgetFeeds['air-quality']}if(!widgetPreferences.f1)delete widgetFeeds.f1;
      saveWidgetPreferences();render();toast('Optional widgets saved, sir.');return;
    }
    if(event.target.id!=='widget-location-search')return;
    event.preventDefault();if(!state.paired)return;
    widgetSearchAbort?.abort();widgetSearchAbort=new AbortController();const generation=++widgetSearchGeneration,button=event.target.querySelector('button');
    button.disabled=true;document.querySelector('#widget-search-status').textContent='Finding matching cities…';document.querySelector('#widget-location-results').replaceChildren();widgetLocations=[];
    try{
      const result=await api('/api/widgets/locations',{method:'POST',body:JSON.stringify({query:new FormData(event.target).get('query').trim()}),signal:AbortSignal.any([widgetSearchAbort.signal,AbortSignal.timeout(12000)])});
      if(generation!==widgetSearchGeneration||state.page!=='system'||!state.paired)return;
      widgetLocations=result.data?.locations||[];
      document.querySelector('#widget-search-status').textContent=result.status==='unavailable'?'City search unavailable. Try again later.':widgetLocations.length?'Choose your city.':'No matching cities. Try adding the country.';
      const list=document.querySelector('#widget-location-results');widgetLocations.forEach((place,index)=>{const item=document.createElement('button');item.type='button';item.dataset.widgetLocation=String(index);item.textContent=place.name;list.append(item)});
    }catch(error){if(generation===widgetSearchGeneration&&error.name!=='AbortError'){const status=document.querySelector('#widget-search-status');if(status)status.textContent='City search unavailable. Try again later.'}}
    finally{if(button.isConnected)button.disabled=false}
  });
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')stopWidgets();else mountWidgets()});
  setInterval(()=>{if(document.visibilityState==='visible')paintRaceCountdown()},1000);
}
