import {CaptureSession, project, orderTargets} from './session.mjs';
import {FEED_URL,validateMaps,validateSnapshot,readBoundedJSON} from './metadata.mjs';
import {createDemo} from './demo.mjs';
import {referenceStore} from './storage.mjs';
import {applyLanguage,translate} from './i18n.mjs';

const $=id=>document.getElementById(id);
const session=new CaptureSession(), demo=createDemo(), references=new Map();
const canvas=$('map-canvas'),ctx=canvas.getContext('2d'),video=$('capture-video');
const sampler=document.createElement('canvas'),sample=sampler.getContext('2d',{willReadFrequently:true});
const worker=new Worker(new URL('./vision-worker.js',import.meta.url),{type:'module'});
let nextId=0,queue=Promise.resolve(),pending=new Map(),workerFailed=false;
let maps=[],engine=null,frame=null,stream=null,timer=null,scanning=false,configuring=0;
let phase='loading',detail='',lastWall=0,language='en',interval=3000,remember=true,revision='bundled';
let metadataKey='Using bundled coordinates';
let crop=null,selection=null,demoMode=false,dimensions='',sourceGeneration=0;
const PREFS='lootlizard.web.preferences.v1',CATALOG='lootlizard.web.catalog.v1';
try {const p=JSON.parse(localStorage.getItem(PREFS)||'null');if(p){language=p.language==='hu'?'hu':'en';interval=[1500,3000,5000].includes(p.interval)?p.interval:3000;}}catch{}
const t=key=>translate(key,language);
const put=(id,value)=>{$(id).textContent=String(value);};
const errorText=error=>String(error?.message||error).slice(0,700);

function request(type,payload={},transfer=[]) {
  const run=()=>new Promise((resolve,reject)=>{
    if(workerFailed){reject(Error('Reload this page to restart the recognition engine.'));return;}
    const id=++nextId;
    const timeout=setTimeout(()=>{
      pending.delete(id);workerFailed=true;worker.terminate();
      for(const p of pending.values()){clearTimeout(p.timeout);p.reject(Error('Recognition engine timed out. Reload this page.'));}
      pending.clear();stop();phase='error';detail='Recognition engine timed out. Reload this page.';render();reject(Error(detail));
    },type==='init'?240000:60000);
    pending.set(id,{resolve,reject,timeout});worker.postMessage({id,type,...payload},transfer);
  });
  const result=queue.then(run);queue=result.catch(()=>{});return result;
}
worker.onmessage=({data})=>{
  if(data.type==='progress'){put('engine-status',data.message);return;}
  const p=pending.get(data.id);if(!p)return;pending.delete(data.id);clearTimeout(p.timeout);
  data.type==='error'?p.reject(Error(data.reason)):p.resolve(data);
};
worker.onerror=event=>{
  workerFailed=true;for(const p of pending.values()){clearTimeout(p.timeout);p.reject(Error(event.message||'Recognition worker failed.'));}pending.clear();
  stop();phase='error';detail='Recognition worker failed. Reload this page.';put('engine-status',detail);render();
};

function savePreferences(){try {if(remember)localStorage.setItem(PREFS,JSON.stringify({language,interval}));else localStorage.removeItem(PREFS);}catch{}}
function currentMap(){return maps.concat(demo.map).find(m=>m.id===session.result?.registration?.mapId)||null;}
function targets(){const map=currentMap();if(!map)return[];const visible=new Map((session.result.points||[]).map(p=>[p.id,p]));return orderTargets(map,session.result.position,session.result.zone).map(p=>({...p,...visible.get(p.id)}));}
function clearGuidance(){session.invalidate();lastWall=0;render();}
function status(next,message=''){phase=next;detail=message;render();}
function updateAge(){const age=lastWall?Date.now()-lastWall:null;put('snapshot-age',age===null?t('No current result'):`${Math.floor(age/1000)} s ${t('ago')}`);return age;}
function render(){
  const result=session.result,map=currentMap(),points=targets();
  const names={loading:'Loading recognition engine…',idle:'Ready when you are',scanning:'Checking image…',recognized:'Map recognized',unknown:'No verified map',stopped:'Sharing stopped',error:'Could not process image',cropping:'Select the complete map'};
  put('recognition-status',t(names[phase]||phase));put('recognition-detail',t(detail||'Open the full map in game. Targets appear automatically when it is recognized.'));
  if(engine&&!workerFailed)put('engine-status',`${t('Local engine ready')} · OpenCV ${engine.opencv}`);
  put('metadata-status',`${t(metadataKey)} · ${revision}`);
  $('recognition-indicator').className=`status-indicator ${map?'is-ready':phase==='error'?'is-error':phase==='scanning'?'is-warning':''}`;
  put('map-name',map?.name||t('Waiting for a map'));put('room-count',points.length);
  put('inside-count',result?.zone?points.filter(p=>p.inside).length:'—');
  put('capture-status',t(session.source==='screen'?'Sharing screen':session.source==='demo'?'Synthetic demo':session.source==='image'?'Local image':'Not sharing'));
  put('position-status',t(result?.position?'Position estimate · identity unverified':'Position unknown · distances unavailable'));
  put('last-update',lastWall?new Date(lastWall).toLocaleTimeString(language==='hu'?'hu-HU':'en-GB'):'—');
  updateAge();
  put('scan-duration',result?.timings?`${Math.round(result.timings.totalMs)} ms`:'—');
  $('start-sharing').disabled=!engine||configuring>0||workerFailed;
  $('stop-sharing').disabled=!session.active;
  $('canvas-empty').hidden=!!frame;$('demo-banner').hidden=!demoMode;
  $('empty-targets').hidden=!!points.length;
  const rows=points.map((p,index)=>{
    const row=document.createElement('tr');if(p.inside)row.className='is-inside';
    for(const value of [index+1,p.name,p.inside===null?'—':t(p.inside?'Inside':'Outside'),p.distance===null?'—':Math.round(p.distance).toLocaleString(language==='hu'?'hu-HU':'en-GB')]){const cell=document.createElement('td');cell.textContent=String(value);row.append(cell);}
    return row;
  });$('target-list').replaceChildren(...rows);draw(points);
}
function draw(points=targets()){
  if(!frame){ctx.clearRect(0,0,canvas.width,canvas.height);return;}
  if(canvas.width!==frame.width||canvas.height!==frame.height){canvas.width=frame.width;canvas.height=frame.height;}
  ctx.putImageData(frame,0,0);const r=session.result;
  const box=canvas.getBoundingClientRect(),unit=1/Math.max(.05,Math.min(box.width/canvas.width,box.height/canvas.height));
  if(r?.registration){
    const matrix=r.registration.matrix;
    if(r.zone){ctx.save();ctx.strokeStyle='#fafafa';ctx.lineWidth=1.5*unit;ctx.setLineDash([7*unit,5*unit]);ctx.beginPath();for(let i=0;i<=100;i++){const a=i*Math.PI/50,p=project(matrix,r.zone.centerX+Math.cos(a)*r.zone.radius,r.zone.centerY+Math.sin(a)*r.zone.radius);if(p)i?ctx.lineTo(...p):ctx.moveTo(...p);}ctx.stroke();ctx.restore();}
    points.forEach((point,index)=>{
      if(!point.visible)return;const p=project(matrix,point.x,point.y);if(!p)return;const[x,y]=p;
      ctx.save();ctx.translate(x,y);ctx.scale(unit,unit);ctx.strokeStyle='#0b1118';ctx.lineWidth=2;ctx.fillStyle=point.inside?'#55e0d0':'#f6bd69';ctx.beginPath();ctx.arc(0,0,3.5,0,Math.PI*2);ctx.fill();ctx.stroke();
      ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(4,-4);ctx.lineTo(10,-13);ctx.stroke();ctx.fillStyle='#101923';ctx.fillRect(8,-28,23,19);ctx.strokeRect(8,-28,23,19);ctx.fillStyle=point.inside?'#55e0d0':'#f6bd69';ctx.font='bold 12px sans-serif';ctx.textAlign='center';ctx.fillText(String(index+1),19.5,-14);ctx.restore();
    });
    if(r.position){const p=project(matrix,r.position.x,r.position.y);if(p){ctx.save();ctx.translate(...p);ctx.scale(unit,unit);ctx.strokeStyle='#7ae8ff';ctx.lineWidth=2;ctx.beginPath();ctx.arc(0,0,7,0,Math.PI*2);ctx.moveTo(-12,0);ctx.lineTo(12,0);ctx.moveTo(0,-12);ctx.lineTo(0,12);ctx.stroke();ctx.font='bold 12px sans-serif';ctx.fillStyle='#7ae8ff';ctx.fillText(t('YOU?'),13,18);ctx.restore();}}
  }
  if(selection){const{x,y,side}=selection;ctx.fillStyle='#45dac627';ctx.fillRect(x,y,side,side);ctx.strokeStyle='#55e0d0';ctx.lineWidth=2;ctx.strokeRect(x,y,side,side);}
}

function stop(){
  sourceGeneration++;clearTimeout(timer);timer=null;session.stop();
  const old=stream;stream=null;if(old)old.getTracks().forEach(track=>track.stop());video.srcObject=null;
  cancelCrop();demoMode=false;dimensions='';lastWall=0;phase='stopped';detail='';render();
}
function schedule(){clearTimeout(timer);if(session.active&&session.source==='screen')timer=setTimeout(scanScreen,interval);}
function capture(){
  if(!video.videoWidth||!video.videoHeight||video.readyState<2)return null;
  const native=`${video.videoWidth}x${video.videoHeight}`;
  if(dimensions&&native!==dimensions)clearGuidance();dimensions=native;
  const scale=Math.min(1,2400/Math.max(video.videoWidth,video.videoHeight),Math.sqrt(4000000/(video.videoWidth*video.videoHeight)));
  sampler.width=Math.max(1,Math.floor(video.videoWidth*scale));sampler.height=Math.max(1,Math.floor(video.videoHeight*scale));
  sample.drawImage(video,0,0,sampler.width,sampler.height);return sample.getImageData(0,0,sampler.width,sampler.height);
}
async function analyze(image){
  const ticket=session.issue();if(!ticket)return null;
  session.result=null;
  frame=new ImageData(new Uint8ClampedArray(image.data),image.width,image.height);status('scanning');
  // Transfer a copy: the displayed frame is retained only on this device.
  const buffer=new Uint8Array(image.data).buffer;
  try{
    const result=await request('analyze',{rgba:buffer,width:image.width,height:image.height,context:$('replay-mode').checked?'replay':'live',ticket},[buffer]);
    if(!session.accept(ticket,result))return null;
    lastWall=Date.now();status(result.registration?'recognized':'unknown',result.registration?'Small anchors mark exact coordinates. Distances are straight-line estimates.':result.reason);return result;
  }catch(error){if(session.accepts(ticket)){session.accept(ticket,null);status('error',errorText(error));}throw error;}
}
async function scanScreen(){
  if(!session.active||session.source!=='screen')return;
  if(scanning||configuring||crop){schedule();return;}
  const track=stream?.getVideoTracks()[0];
  if(!track||track.readyState!=='live'){stop();return;}
  if(track.muted){clearGuidance();status('unknown','Screen capture is paused.');schedule();return;}
  scanning=true;try{const image=capture();if(image)await analyze(image);else{clearGuidance();status('unknown','Waiting for a readable shared image…');}}catch{}finally{scanning=false;schedule();}
}
async function setWorkerReferences(useDemo=demoMode){
  const records=useDemo?[{mapId:'demo',image:demo.reference}]:[...references].map(([mapId,r])=>({mapId,image:r.image}));
  const transfer=[];const payload=records.map(({mapId,image})=>{const rgba=new Uint8Array(image.data).buffer;transfer.push(rgba);return{mapId,rgba,width:image.width,height:image.height};});
  return request('references',{references:payload},transfer);
}
async function attachStream(media,token,useDemo=false){
  if(token!==sourceGeneration){media.getTracks().forEach(t=>t.stop());return;}
  stream=media;video.srcObject=media;const track=media.getVideoTracks()[0];if(!track){stop();throw Error('No video track was selected.');}
  track.addEventListener('ended',()=>{if(stream===media)stop();});
  track.addEventListener('mute',()=>{if(stream===media){clearGuidance();status('unknown','Screen capture is paused.');}});
  track.addEventListener('unmute',()=>{if(stream===media){clearGuidance();schedule();}});
  try{
    await video.play();await setWorkerReferences(useDemo);
    if(token!==sourceGeneration||track.readyState!=='live')return;
    session.begin('screen');demoMode=useDemo;status('unknown','Open the full map in game. Targets appear automatically when it is recognized.');scanScreen();
  }catch(error){if(stream===media)stop();throw error;}
}
function startSharing(){
  // The picker must run directly inside the click's transient user activation.
  stop();const token=sourceGeneration;
  if(!navigator.mediaDevices?.getDisplayMedia){status('error','Screen sharing needs a supported desktop browser on HTTPS or localhost.');return;}
  const picked=navigator.mediaDevices.getDisplayMedia({video:{frameRate:{ideal:3,max:5}},audio:false,selfBrowserSurface:'exclude'});
  status('idle','Choose the screen where PUBG is running.');
  picked.then(media=>attachStream(media,token)).catch(error=>{if(token===sourceGeneration)status('error',errorText(error));});
}
async function analyzeImageData(image,{source='image'}={}){
  stop();const token=sourceGeneration;await ready;if(token!==sourceGeneration)return null;demoMode=source==='demo';
  configuring++;try{await setWorkerReferences(demoMode);}finally{configuring--;}
  if(token!==sourceGeneration)return null;session.begin(source);return analyze(image);
}
async function loadDemo(){return analyzeImageData(demo.mapFrame,{source:'demo'});}

async function decodeImage(blob,maxSide=1800){
  if(!['image/png','image/jpeg'].includes(blob.type)||blob.size>64000000)throw Error('Choose a PNG or JPEG smaller than 64 MB.');
  const image=await createImageBitmap(blob);
  try{
    if(image.width*image.height>40000000||Math.max(image.width,image.height)>8192)throw Error('Image dimensions are too large.');
    const scale=Math.min(1,maxSide/Math.max(image.width,image.height),Math.sqrt(4000000/(image.width*image.height)));
    const c=document.createElement('canvas');c.width=Math.round(image.width*scale);c.height=Math.round(image.height*scale);
    const cctx=c.getContext('2d',{willReadFrequently:true});cctx.fillStyle='#000';cctx.fillRect(0,0,c.width,c.height);cctx.drawImage(image,0,0,c.width,c.height);
    return cctx.getImageData(0,0,c.width,c.height);
  }finally{image.close();}
}
async function imageBlob(image){const c=document.createElement('canvas');c.width=image.width;c.height=image.height;c.getContext('2d').putImageData(image,0,0);return new Promise((resolve,reject)=>c.toBlob(blob=>blob?resolve(blob):reject(Error('Could not store reference.')),'image/png'));}
async function addReference(mapId,image){
  if(!maps.some(m=>m.id===mapId))throw Error('Choose an available map first.');
  if(Math.abs(image.width/image.height-1)>.015||Math.min(image.width,image.height)<128)throw Error('Use the complete square map, at least 128 pixels wide.');
  if(!references.has(mapId)&&references.size>=8)throw Error('At most eight map references can be loaded.');
  const old=references.get(mapId);configuring++;clearGuidance();references.set(mapId,{image});
  try{await setWorkerReferences();}catch(error){old?references.set(mapId,old):references.delete(mapId);throw error;}finally{configuring--;renderReferences();render();}
  if(remember){try{await referenceStore('put',{mapId,blob:await imageBlob(image)});}catch{put('reference-status',t('Loaded for this session; browser storage is unavailable.'));}}
  if(session.source==='image'&&frame)await analyze(frame);else schedule();
}
function renderReferences(){
  const list=[...references].map(([id,r])=>{const li=document.createElement('li');li.textContent=`${maps.find(m=>m.id===id)?.name||id} · ${r.image.width} × ${r.image.height}`;return li;});
  $('reference-list').replaceChildren(...list);$('clear-references').disabled=!references.size;
  put('reference-status',references.size?`${references.size} ${t('map references loaded')}`:t('No references loaded'));
  const selected=$('reference-map').value;$('reference-map').replaceChildren(...maps.map(map=>{const o=document.createElement('option');o.value=map.id;o.textContent=map.name;return o;}));if(maps.some(m=>m.id===selected))$('reference-map').value=selected;
}
function cancelCrop(){crop=null;selection=null;canvas.classList.remove('is-cropping');for(const id of ['save-crop','cancel-crop','crop-help'])if($(id))$(id).hidden=true;}
function startCrop(){if(!frame){status('idle','Start sharing or open an image before selecting a reference.');return;}clearGuidance();crop={image:frame,mapId:$('reference-map').value};selection=null;canvas.classList.add('is-cropping');for(const id of ['save-crop','cancel-crop','crop-help'])$(id).hidden=false;status('cropping','Drag a square around the complete, fully zoomed-out map, then save.');}
function canvasPoint(event){const box=canvas.getBoundingClientRect(),scale=Math.min(box.width/canvas.width,box.height/canvas.height);const left=box.left+(box.width-canvas.width*scale)/2,top=box.top+(box.height-canvas.height*scale)/2;return{x:Math.max(0,Math.min(canvas.width,(event.clientX-left)/scale)),y:Math.max(0,Math.min(canvas.height,(event.clientY-top)/scale))};}
canvas.addEventListener('pointerdown',event=>{if(!crop)return;crop.start=canvasPoint(event);canvas.setPointerCapture(event.pointerId);});
canvas.addEventListener('pointermove',event=>{if(!crop?.start||!canvas.hasPointerCapture(event.pointerId))return;const p=canvasPoint(event),s=crop.start;const side=Math.min(Math.abs(p.x-s.x),Math.abs(p.y-s.y));selection={x:Math.round(p.x<s.x?s.x-side:s.x),y:Math.round(p.y<s.y?s.y-side:s.y),side:Math.round(side)};draw();});
async function saveCrop(){if(!selection||selection.side<128){status('cropping','Select a square at least 128 pixels wide.');return;}const{mapId,image}=crop,{x,y,side}=selection;const c=document.createElement('canvas');c.width=image.width;c.height=image.height;c.getContext('2d').putImageData(image,0,0);const out=document.createElement('canvas');out.width=out.height=Math.min(side,1800);out.getContext('2d').drawImage(c,x,y,side,side,0,0,out.width,out.height);const ref=out.getContext('2d').getImageData(0,0,out.width,out.height);cancelCrop();await addReference(mapId,ref);status('idle','Reference ready. Open the map in game to recognize it.');}

async function updateMetadata(){
  let snapshot;
  try{snapshot=validateSnapshot(await readBoundedJSON(await fetch(FEED_URL,{credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(8000)})));}
  catch{metadataKey='Using saved coordinates';render();return;}
  if(JSON.stringify(snapshot.maps)===JSON.stringify(maps)){revision=snapshot.revision;metadataKey='GitHub coordinates';render();return;}
  configuring++;clearGuidance();const previous=maps;maps=snapshot.maps;
  try{
    await request('init',{maps:[...maps,demo.map]});for(const id of references.keys())if(!maps.some(m=>m.id===id))references.delete(id);
    await setWorkerReferences();revision=snapshot.revision;
    if(remember)try{localStorage.setItem(CATALOG,JSON.stringify(snapshot));}catch{}
    metadataKey='GitHub coordinates';
  }catch(error){maps=previous;status('error',errorText(error));}
  finally{configuring--;renderReferences();render();schedule();}
}

$('start-sharing').addEventListener('click',startSharing);$('stop-sharing').addEventListener('click',stop);
$('load-demo').addEventListener('click',()=>loadDemo().catch(e=>status('error',errorText(e))));
$('open-image').addEventListener('change',async event=>{const file=event.target.files[0];event.target.value='';if(!file)return;stop();const token=sourceGeneration;try{const image=await decodeImage(file,2400);if(token===sourceGeneration)await analyzeImageData(image);}catch(e){if(token===sourceGeneration)status('error',errorText(e));}});
$('reference-file').addEventListener('change',async event=>{const file=event.target.files[0];event.target.value='';if(file)try{await ready;await addReference($('reference-map').value,await decodeImage(file));}catch(e){put('reference-status',errorText(e));}});
$('clear-references').addEventListener('click',async()=>{configuring++;clearGuidance();try{await request('references',{references:[]});references.clear();await referenceStore('clear');}catch(e){put('reference-status',errorText(e));}finally{configuring--;renderReferences();render();schedule();}});
$('crop-reference')?.addEventListener('click',startCrop);$('save-crop')?.addEventListener('click',()=>saveCrop().catch(e=>put('reference-status',errorText(e))));$('cancel-crop')?.addEventListener('click',()=>{cancelCrop();render();schedule();});
$('language-select').value=language;$('scan-interval').value=String(interval);
$('language-select').addEventListener('change',()=>{language=$('language-select').value;applyLanguage(language);savePreferences();renderReferences();render();});
$('scan-interval').addEventListener('change',()=>{interval=Number($('scan-interval').value);savePreferences();schedule();});
$('cache-preferences').addEventListener('change',async()=>{remember=$('cache-preferences').checked;savePreferences();try{if(!remember){localStorage.removeItem(CATALOG);await referenceStore('clear');}else{for(const[mapId,r]of references)await referenceStore('put',{mapId,blob:await imageBlob(r.image)});}}catch{}});
$('replay-mode').addEventListener('change',()=>{clearGuidance();if(session.active&&session.source!=='screen'&&frame)analyze(frame).catch(()=>{});else schedule();});
window.addEventListener('pagehide',stop);
new ResizeObserver(()=>draw()).observe($('map-stage'));
setInterval(()=>{
  const age=updateAge();
  if(session.source==='screen'&&age!==null&&age>Math.max(15000,interval*3)&&session.result){clearGuidance();status('unknown','The last result expired. Waiting for a fresh frame.');}
},1000);

const ready=(async()=>{
  applyLanguage(language);render();
  maps=validateMaps(await Promise.all(['erangel','taego'].map(async id=>readBoundedJSON(await fetch(`../../data/${id}.json`)))));
  try{const cached=JSON.parse(localStorage.getItem(CATALOG)||'null');if(cached){validateSnapshot(cached);maps=cached.maps;revision=cached.revision;}}catch{}
  const response=await request('init',{maps:[...maps,demo.map]});engine=response.capabilities;
  put('engine-status',`${t('Local engine ready')} · OpenCV ${engine.opencv}`);
  try{const saved=await referenceStore('read');for(const record of saved.slice(0,8)){if(maps.some(m=>m.id===record.mapId))references.set(record.mapId,{image:await decodeImage(record.blob)});}await setWorkerReferences(false);}catch{references.clear();}
  renderReferences();status('idle');updateMetadata().catch(()=>{});setInterval(()=>updateMetadata().catch(()=>{}),60000);return response;
})();
ready.catch(error=>{status('error',errorText(error));put('engine-status',t('Engine unavailable. Reload to retry.'));});
const api={ready,demo:loadDemo,analyzeImageData,stop,getState:()=>({...session.snapshot(),phase,mapId:currentMap()?.id||null,points:targets(),position:session.result?.position||null,zone:session.result?.zone||null,engine})};
if(['127.0.0.1','localhost'].includes(location.hostname)&&new URLSearchParams(location.search).get('test')==='1')api.startTestStream=async (media,{demo:synthetic=false}={})=>{stop();const token=sourceGeneration;await ready;await attachStream(media,token,synthetic);};
window.lootLizardPoc=Object.freeze(api);
