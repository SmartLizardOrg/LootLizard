/** Deterministic original artwork: exercises real CV, contains no PUBG imagery. */
export function createDemo() {
  const side = 640, canvas = document.createElement('canvas'); canvas.width=canvas.height=side;
  const ctx=canvas.getContext('2d',{willReadFrequently:true}), image=ctx.createImageData(side,side);
  let seed=127291;
  const random=()=>{ seed=(Math.imul(seed,1664525)+1013904223)>>>0; return seed/4294967296; };
  for(let y=0;y<side;y++) for(let x=0;x<side;x++) {
    const n=Math.floor(38+random()*57), i=(y*side+x)*4;
    image.data.set([n*.63|0,n,n*.77|0,255],i);
  }
  ctx.putImageData(image,0,0);
  // Distributed distinct structures, similar in scale to terrain/road features.
  for(let i=0;i<430;i++) {
    const x=random()*side,y=random()*side,r=2+random()*12;
    ctx.fillStyle=`rgb(${40+random()*90|0},${45+random()*70|0},${40+random()*70|0})`;
    if(i%2) ctx.fillRect(x,y,r*1.5,r); else {ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();}
  }
  for(let i=0;i<11;i++) {ctx.strokeStyle=i%2?'#a1a394':'#343e38';ctx.lineWidth=i%2?2:5;ctx.beginPath();ctx.moveTo(random()*side,0);ctx.bezierCurveTo(random()*side,side/3,random()*side,side*.7,random()*side,side);ctx.stroke();}
  ctx.font='bold 13px sans-serif';ctx.fillStyle='#c5c6b6';
  [['NORTH POINT',54,88],['OLD HARBOUR',368,170],['GREEN VALLEY',130,470],['EAST RIDGE',400,551]].forEach(([t,x,y])=>ctx.fillText(t,x,y));
  const reference=ctx.getImageData(0,0,side,side);
  const frameCanvas=document.createElement('canvas');frameCanvas.width=960;frameCanvas.height=720;
  const f=frameCanvas.getContext('2d',{willReadFrequently:true});f.fillStyle='#0e1720';f.fillRect(0,0,960,720);f.drawImage(canvas,160,40);
  f.fillStyle='#a4b3bd';f.font='12px sans-serif';f.fillText('SYNTHETIC FIXTURE · ORIGINAL GENERATED ARTWORK',18,20);
  // A unique round marker with a broad, bordered viewing fan.
  const mx=160+260,my=40+320;
  f.fillStyle='#777777';f.beginPath();f.moveTo(mx,my);f.arc(mx,my,58,Math.PI,Math.PI*1.5);f.closePath();f.fill();
  f.strokeStyle='#e1e1e1';f.lineWidth=2;f.beginPath();f.moveTo(mx-58,my);f.lineTo(mx,my);f.lineTo(mx,my-58);f.stroke();
  f.fillStyle='rgb(200,188,35)';f.strokeStyle='white';f.lineWidth=2;f.beginPath();f.arc(mx,my,12,0,Math.PI*2);f.fill();f.stroke();
  f.fillStyle='white';f.beginPath();f.arc(mx,my,1.2,0,Math.PI*2);f.fill();
  f.strokeStyle='#f5f5f5';f.lineWidth=3;f.beginPath();f.arc(160+330,40+310,190,0,Math.PI*2);f.stroke();
  const mapFrame=f.getImageData(0,0,960,720);
  f.fillStyle='#29363d';f.fillRect(0,0,960,720);f.fillStyle='#526b70';f.fillRect(0,350,960,370);f.fillStyle='#758b92';f.fillRect(0,0,960,200);
  f.fillStyle='#1f2a30';f.fillRect(390,300,190,420);f.fillStyle='#ccd4d6';f.font='20px sans-serif';f.fillText('NO MAP VISIBLE — SYNTHETIC GAMEPLAY',200,90);
  const gameplay=f.getImageData(0,0,960,720);
  const map={id:'demo',name:'Synthetic demo',size_m:8000,source:{url:'https://github.com/molnard-labs/LootLizard',license:'MIT',notes:'Original deterministic test artwork. Not a PUBG map.'},points:[
    {id:'demo-01',name:'Demo room 01',x:.43,y:.48},{id:'demo-02',name:'Demo room 02',x:.61,y:.57},
    {id:'demo-03',name:'Demo room 03',x:.2,y:.23},{id:'demo-04',name:'Demo room 04',x:.81,y:.79},
    {id:'demo-05',name:'Demo room 05',x:.51,y:.32},{id:'demo-06',name:'Demo room 06',x:.23,y:.63},
  ]};
  return {reference,map,frames:[mapFrame,gameplay,mapFrame],mapFrame,gameplay};
}
