// Headless browser regressions against ui_fixture.py; never use on real service.
import {spawn} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve, basename} from 'node:path';
import assert from 'node:assert/strict';

const base = process.argv[2] || 'http://127.0.0.1:8799';
const out = resolve(process.argv[3] || 'test-results');
if (!base.endsWith(':8799')) throw new Error('Use the isolated fixture on 8799 only');
mkdirSync(out,{recursive:true});
const profile = mkdtempSync(join(tmpdir(),'aula-ui-check-'));
const proc = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',[
  '--headless=new','--enable-unsafe-swiftshader','--no-first-run','--no-default-browser-check',
  '--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'
],{stdio:'ignore',windowsHide:true});
const sleep = ms => new Promise(r=>setTimeout(r,ms));
let ws, next=0;
const pending = new Map(), errors=[], checks=[];
let resumeAt=process.env.KEYLIGHT_BROWSER_FROM || '';
let beforeDialogue;
async function send(method,params={}) {
  const id=++next;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP timed out: ${method}`));},8000);
    pending.set(id,{resolve,reject,timer});
    ws.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression) {
  const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  if(r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result?.value;
}
async function until(expression) {
  for(let i=0;i<60;i++){if(await evaluate(expression))return;await sleep(100);}
  throw new Error(`Condition timed out: ${expression}`);
}
async function check(name,fn) {
  if(resumeAt){if(name!==resumeAt)return;resumeAt='';}
  try { await fn(); checks.push(name);process.stdout.write(`PASS ${name}\n`); }
  catch (err) {
    const state=await evaluate(`({shareRevision,shareBusy,status:$('share-status').textContent,dialogOpen:$('share-dialog').open,shareCode:$('share-code').value.slice(0,30),inspectDisabled:$('share-inspect').disabled,selectedPreset:app.selectedPreset,params:app.params})`).catch(()=>null);
    const splash=await evaluate(`({metrics:window.keylightSplash?.metrics(),surface:!!document.getElementById('splash'),canvas:!!document.getElementById('splash-canvas'),ready:document.readyState})`).catch(()=>null);
    writeFileSync(join(out,'failure.json'),JSON.stringify({name,error:String(err),state,splash,errors},null,2));
    throw err;
  }
}
let navigation = 0;
function freshUrl(url) { const next=new URL(url);next.searchParams.set('qaPage',String(++navigation));return next.href; }
async function navigateWorkspace(url) {
  await send('Page.navigate',{url:freshUrl(url)});
  await until(`window.keylightSplash?.metrics().phase==='active'`);
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await until(`window.keylightSplash?.metrics().phase==='entered'`);
}
try {
  let port;
  for(let i=0;i<60;i++){
    try{port=Number(readFileSync(join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]);break;}catch{await sleep(100);}
  }
  if(!port)throw new Error('Chrome did not start');
  const tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  ws.onmessage=ev=>{
    const m=JSON.parse(ev.data);
    if(m.id&&pending.has(m.id)){
      const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);
      if(m.error)p.reject(new Error(JSON.stringify(m.error)));else p.resolve(m.result || {});
    }
    if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  };
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
  await send('Emulation.setDeviceMetricsOverride',{width:1500,height:950,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:freshUrl(base+'/#/studio')});
  if(process.env.KEYLIGHT_BROWSER_FROM)await navigateWorkspace(base+'/#/studio');
  await check('launch sphere is visible, animated and isolates the existing workspace',async()=>{
    await until(`window.keylightSplash?.metrics().frames>4&&document.getElementById('device-name')?.textContent.includes('Fake')`);
    assert.equal(await evaluate(`$('workspace').inert`),true);
    assert.equal(await evaluate(`getComputedStyle($('workspace')).visibility`),'hidden');
    assert.match(await evaluate(`$('splash').textContent`),/键光.*让灵感/s);
    const metrics=await evaluate(`keylightSplash.metrics()`);
    assert.ok(metrics.particles>=1300&&metrics.pendingFrame);
    if(metrics.renderer==='webgl'&&!metrics.lowPower)assert.ok(metrics.particles>24000);
    writeFileSync(join(out,'splash-initial.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
  });
  await check('planet and text stay fixed while attraction follows and holds without a timed recoil',async()=>{
    const wordmark=await evaluate(`(()=>{const r=document.querySelector('.splash-wordmark').getBoundingClientRect();return{x:r.x,y:r.y};})()`);
    const start=await evaluate(`keylightSplash.metrics().time`);
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:975,y:370});
    await until(`keylightSplash.metrics().pointer.force>.2`);
    const a=await evaluate(`keylightSplash.metrics()`);
    assert.ok(a.pointer.x>0&&a.pointer.x<a.target.x*.85);
    const gain=-Math.log(1-a.pointer.x/a.target.x)/(a.time-start);
    assert.ok(gain>2.5&&gain<4.6,`pointer response gain ${gain}`);
    assert.deepEqual(a.center,{x:0,y:0});
    writeFileSync(join(out,'splash-interaction.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    await sleep(2100);
    const settled=await evaluate(`keylightSplash.metrics()`);
    assert.ok(settled.pointer.force>.98&&Math.abs(settled.pointer.x-settled.target.x)<.02);
    assert.deepEqual(settled.center,{x:0,y:0});
    assert.deepEqual(await evaluate(`(()=>{const r=document.querySelector('.splash-wordmark').getBoundingClientRect();return{x:r.x,y:r.y};})()`),wordmark);
    for(let i=0;i<6;i++)await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:975+(i%2),y:370});
    await sleep(250);assert.ok((await evaluate(`keylightSplash.metrics()`)).pointer.force>.98);
    writeFileSync(join(out,'splash-held.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    const beforeReturn=await evaluate(`keylightSplash.sample().reduce((s,p)=>s+Math.hypot(p.dx,p.dy),0)/keylightSplash.sample().length`);
    await evaluate(`$('splash').dispatchEvent(new PointerEvent('pointerleave'))`);
    await sleep(750);
    const afterReturn=await evaluate(`keylightSplash.sample().reduce((s,p)=>s+Math.hypot(p.dx,p.dy),0)/keylightSplash.sample().length`);
    assert.ok(afterReturn<beforeReturn*.12,`fast return ${beforeReturn} -> ${afterReturn}`);
    await until(`keylightSplash.metrics().pointer.force<.025`);
    assert.equal(await evaluate(`keylightSplash.metrics().target.force`),0);
    assert.ok(Math.abs((await evaluate(`keylightSplash.metrics()`)).center.x)<.025);
  });
  await check('one particle pool follows and diffuses across the edge and subsequent direction changes',async()=>{
    assert.equal(await evaluate(`keylightSplash.metrics().surfaceLayers`),1);
    const initial=await evaluate(`keylightSplash.sample()`);
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:1020,y:465});
    await until(`keylightSplash.metrics().pointer.force>.8`);
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:1250,y:430});
    await until(`keylightSplash.metrics().pointer.x>1.4`);
    const m=await evaluate(`keylightSplash.metrics()`);
    assert.ok(m.pointer.force>.5);
    assert.deepEqual(m.center,{x:0,y:0});
    await sleep(800);
    const held=await evaluate(`keylightSplash.metrics()`);
    assert.ok(held.pointer.force>.5);
    assert.ok(Math.abs(held.pointer.x-held.target.x)<.02);
    writeFileSync(join(out,'splash-outside.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    for(const [x,y] of [[1350,350],[1300,260],[1150,240],[1100,330]]){
      await send('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});await sleep(220);
    }
    const moved=await evaluate(`keylightSplash.sample()`);
    const original=new Map(initial.map(p=>[p.id,p]));
    const displaced=moved.filter(p=>original.has(p.id)&&Math.hypot(p.dx-original.get(p.id).dx,p.dy-original.get(p.id).dy)>.025);
    assert.ok(displaced.length>5,'the original particles themselves must move, including after crossing the edge');
    assert.ok(moved.every(p=>[p.x,p.y,p.dx,p.dy].every(Number.isFinite)));
    assert.ok(moved.every(p=>Math.hypot(p.dx,p.dy)<=.441),'diffusion must stay within the smaller halo');
    writeFileSync(join(out,'splash-far-follow.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    await evaluate(`$('splash').dispatchEvent(new PointerEvent('pointerleave'))`);
    await until(`keylightSplash.metrics().pointer.force<.025`);
  });
  await check('a distant cursor smoothly releases particles back to the same spherical surface',async()=>{
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:980,y:420});await sleep(450);
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:1190,y:350});await sleep(650);
    const displaced=await evaluate(`keylightSplash.sample().reduce((s,p)=>s+Math.hypot(p.dx,p.dy),0)/keylightSplash.sample().length`);
    assert.ok(displaced>.015);
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:1480,y:50});
    await until(`keylightSplash.metrics().target.force===0&&keylightSplash.metrics().pointer.force<.025`);
    await sleep(1600);
    const restored=await evaluate(`keylightSplash.sample()`);
    const remaining=restored.reduce((s,p)=>s+Math.hypot(p.dx,p.dy),0)/restored.length;
    assert.ok(remaining<displaced*.1,`mean offset ${displaced} -> ${remaining}`);
    assert.ok(restored.every(p=>Math.hypot(p.x,p.y)<1.04),'the far cursor must leave a spherical silhouette');
    writeFileSync(join(out,'splash-distant-restored.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
  });
  await check('splash resizes for mobile and caps high-DPI rendering resolution',async()=>{
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:3,mobile:false});
    await until(`keylightSplash.metrics().width===390`);
    const m=await evaluate(`keylightSplash.metrics()`);
    assert.ok(m.dpr<=1.8&&m.canvasWidth<=702&&m.canvasHeight<=1520);
    assert.equal(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),true);
    writeFileSync(join(out,'splash-mobile.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    await send('Emulation.setDeviceMetricsOverride',{width:1500,height:950,deviceScaleFactor:1,mobile:false});
  });
  await check('entry uses slower key formation and fade, then releases resources within 1.65 seconds',async()=>{
    const before=await evaluate(`JSON.stringify(app.params)`);
    const point=await evaluate(`(()=>{const b=document.querySelector('[data-view="ai"]').getBoundingClientRect();return{x:b.x+b.width/2,y:b.y+b.height/2};})()`);
    await evaluate(`window.splashEntries=0;window.leakedSplashClicks=0;window.addEventListener('keylight:entered',()=>splashEntries++);document.querySelector('[data-view="ai"]').addEventListener('click',()=>leakedSplashClicks++);window.splashGL=$('splash-canvas').getContext('webgl');window.splashEnterStart=performance.now()`);
    await evaluate(`window.entryFrames=[];(function observe(){const m=keylightSplash.metrics();if(m.phase==='leaving')entryFrames.push({entry:m.entry,width:m.width,height:m.height,inert:$('workspace').inert,points:keylightSplash.sample()});if(m.phase!=='entered')requestAnimationFrame(observe);})()`);
    for(let i=0;i<2;i++) {
      await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
      await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
    }
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await until(`keylightSplash.metrics().phase==='entered'`);
    const elapsed=await evaluate(`performance.now()-splashEnterStart`);
    assert.ok(elapsed>=1500&&elapsed<2300,elapsed);
    const sequence=await evaluate(`entryFrames`);
    writeFileSync(join(out,'entry-trajectory.json'),JSON.stringify(sequence,null,2));
    assert.ok(sequence.length>=3,'collect actual animation frames');
    assert.ok(sequence.every(f=>f.inert&&f.entry.keyboard),'the interface stays inert throughout assembly');
    const assembled=sequence.findLast(f=>f.entry.progress>=.86);
    assert.ok(assembled,'particles must resolve before the final crossfade');
    const rect=assembled.entry.rect,radius=Math.min(assembled.width*.38,assembled.height*.34,320);
    for(const p of assembled.points){
      const x=assembled.width/2+p.x*radius-rect.x,y=assembled.height*.49-p.y*radius-rect.y;
      assert.ok(x>=0&&x<=rect.width&&y>=0&&y<=rect.height,'particle lands inside real keyboard');
      const pad=Math.min(9,rect.width*.03),cw=(rect.width-pad*2)/22,ch=(rect.height-pad*2)/5;
      const gap=Math.max(1,Math.min(2.1,cw*.16)),col=p.id%22,row=Math.floor((p.id%110)/22);
      assert.ok(x>=pad+col*cw+gap-.02&&x<=pad+(col+1)*cw-gap+.02,'correct key column');
      assert.ok(y>=pad+row*ch+gap-.02&&y<=pad+(row+1)*ch-gap+.02,'correct key row');
    }
    writeFileSync(join(out,'entry-trajectory.json'),JSON.stringify(sequence,null,2));
    assert.equal(await evaluate(`splashEntries`),1);assert.equal(await evaluate(`leakedSplashClicks`),0);
    assert.equal(await evaluate(`app.view`),'studio');assert.equal(await evaluate(`JSON.stringify(app.params)`),before);
    const m=await evaluate(`keylightSplash.metrics()`);
    assert.equal(m.resourcesReleased,true);assert.equal(m.pendingFrame,false);assert.equal(m.listeners,0);assert.equal(m.canvasWidth,0);
    if(await evaluate(`!!splashGL`)) assert.equal(await evaluate(`splashGL.isContextLost()`),true);
    await sleep(200);assert.equal(await evaluate(`keylightSplash.metrics().frames`),m.frames);
    assert.equal(await evaluate(`$('workspace').inert`),false);
    assert.equal(await evaluate(`getComputedStyle(document.activeElement).outlineStyle`),'none');
  });
  await check('keyboard destinations follow a window resize during assembly',async()=>{
    await send('Page.navigate',{url:freshUrl(base+'/#/studio')});
    await until(`window.keylightSplash?.metrics().frames>2`);
    await evaluate(`$('splash').click()`);await sleep(100);
    await send('Emulation.setDeviceMetricsOverride',{width:1380,height:900,deviceScaleFactor:2,mobile:false});
    const result=await evaluate(`new Promise(resolve=>{function observe(){const m=keylightSplash.metrics();if(m.entry.progress>.65||m.phase==='entered'){const r=$('board').getBoundingClientRect();resolve({m,rect:{x:r.x,y:r.y,width:r.width,height:r.height},points:keylightSplash.sample()});}else requestAnimationFrame(observe);}observe();})`);
    assert.equal(result.m.phase,'leaving');assert.equal(result.m.width,1380);
    assert.deepEqual(result.m.entry.rect,result.rect);
    assert.ok(result.points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
    await until(`keylightSplash.metrics().phase==='entered'`);
    await send('Emulation.setDeviceMetricsOverride',{width:1500,height:950,deviceScaleFactor:1,mobile:false});
  });
  await check('context loss during assembly still finishes and releases fallback resources',async()=>{
    await send('Page.navigate',{url:freshUrl(base+'/#/studio')});await until(`window.keylightSplash?.metrics().frames>2`);
    await evaluate(`$('splash').click();$('splash-canvas').getContext('webgl')?.getExtension('WEBGL_lose_context').loseContext()`);
    await until(`keylightSplash.metrics().phase==='entered'`);
    const m=await evaluate(`keylightSplash.metrics()`);
    assert.equal(m.renderer,'canvas2d');assert.ok(m.resourcesReleased&&!m.pendingFrame&&m.listeners===0);
  });
  await check('changing to reduced motion during assembly finishes immediately',async()=>{
    await send('Page.navigate',{url:freshUrl(base+'/#/studio')});await until(`window.keylightSplash?.metrics().frames>2`);
    await evaluate(`$('splash').click()`);
    await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    await until(`keylightSplash.metrics().phase==='entered'`);
    assert.equal(await evaluate(`$('workspace').inert`),false);
    await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
  });
  await check('entry preserves the AI route and fades when no studio keyboard is visible',async()=>{
    await send('Page.navigate',{url:freshUrl(base+'/#/ai')});await until(`window.keylightSplash?.metrics().frames>2&&app.view==='ai'`);
    await evaluate(`$('splash').click()`);
    assert.equal(await evaluate(`keylightSplash.metrics().entry.keyboard`),false);
    await until(`keylightSplash.metrics().phase==='entered'`);
    assert.equal(await evaluate(`app.view`),'ai');
  });
  await check('reduced motion shows a static sphere and Space still enters',async()=>{
    await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    await send('Page.navigate',{url:freshUrl(base+'/#/studio')});
    await until(`window.keylightSplash?.metrics().phase==='active'&&keylightSplash.metrics().reducedMotion&&keylightSplash.metrics().frames>=1`);
    const a=await evaluate(`keylightSplash.metrics()`);assert.equal(a.pendingFrame,false);
    await sleep(200);assert.equal(await evaluate(`keylightSplash.metrics().frames`),a.frames);
    writeFileSync(join(out,'splash-reduced-motion.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:' ',code:'Space',windowsVirtualKeyCode:32});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:' ',code:'Space',windowsVirtualKeyCode:32});
    await until(`keylightSplash.metrics().phase==='entered'`);
    await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
  });
  await check('WebGL loss degrades to Canvas and touch can interact and enter',async()=>{
    await send('Page.navigate',{url:freshUrl(base+'/#/studio')});await until(`window.keylightSplash?.metrics().phase==='active'&&keylightSplash.metrics().frames>2`);
    if(await evaluate(`keylightSplash.metrics().renderer==='webgl'`)) {
      await evaluate(`$('splash-canvas').getContext('webgl').getExtension('WEBGL_lose_context').loseContext()`);
      await until(`keylightSplash.metrics().renderer==='canvas2d'`);
    }
    await send('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
    await send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:900,y:430}]});
    await until(`keylightSplash.metrics().target.force>0`);
    await send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:930,y:410}]});
    await until(`keylightSplash.metrics().target.force>0`);
    await send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    await sleep(180);
    assert.equal(await evaluate(`keylightSplash.metrics().phase`),'active','touch drag must not synthesize an entry click');
    if(await evaluate(`keylightSplash.metrics().phase==='active'`)) {
      await send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:750,y:475}]});
      await send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    }
    await until(`keylightSplash.metrics().phase==='entered'`);
    await send('Emulation.setTouchEmulationEnabled',{enabled:false});
  });
  await check('unavailable graphics still show a static particle sphere and Enter works',async()=>{
    const hook=await send('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(...args){return this.id==='splash-canvas'?null:original.apply(this,args);};})()`});
    await send('Page.navigate',{url:freshUrl(base+'/#/studio')});
    await until(`window.keylightSplash?.metrics().renderer==='static'`);
    assert.equal(await evaluate(`keylightSplash.metrics().pendingFrame`),false);
    assert.ok(await evaluate(`document.querySelectorAll('.splash-static circle').length>500`));
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await until(`keylightSplash.metrics().phase==='entered'`);
    await send('Page.removeScriptToEvaluateOnNewDocument',{identifier:hook.identifier});
  });
  await check('boot and connect to fake device',async()=>{
    await until(`document.getElementById('device-name')?.textContent.includes('Fake')`);
    assert.equal(await evaluate(`app.params.effect`),'rainbow');
  });
  await check('AI card opens creation without an existing expression or error',async()=>{
    await evaluate(`document.querySelector('[data-effect="ai"]').click()`);
    await until(`app.view==='ai'&&$('ai-status').textContent.includes('预览')`);
    assert.equal(await evaluate(`app.params.effect`),'rainbow');
    assert.equal(await evaluate(`app.aiSpec`),null);
    await evaluate(`showView('studio')`);
  });
  await check('merged sliders preserve speed and brightness',async()=>{
    await evaluate(`$('speed').value=.6;$('speed').dispatchEvent(new Event('input'));$('brightness').value=.42;$('brightness').dispatchEvent(new Event('input'));`);
    await until(`fetch('/api/state').then(r=>r.json()).then(s=>s.params.speed===.6&&s.params.brightness===.42)`);
  });
  await check('restore firmware stops frame count',async()=>{
    await evaluate(`$('release').click()`);
    await until(`app.device?.control==='firmware'`);
    const before=await evaluate(`fetch('/api/state').then(r=>r.json()).then(s=>s.device.frames_sent)`);
    await sleep(200);
    assert.equal(await evaluate(`fetch('/api/state').then(r=>r.json()).then(s=>s.device.frames_sent)`),before);
    assert.match(await evaluate(`$('mode-badge').textContent`),/固件/);
  });
  await check('effect selection resumes software streaming',async()=>{
    await evaluate(`document.querySelector('[data-effect="breathe"]').click()`);
    await until(`app.device?.control==='software'&&app.params.effect==='breathe'`);
  });
  await check('ripple uses the new name and selects the compatible effect id',async()=>{
    assert.equal(await evaluate(`document.querySelector('[data-effect="ripple"] span').textContent`),'涟漪');
    await evaluate(`document.querySelector('[data-effect="ripple"]').click()`);
    await until(`app.params.effect==='ripple'`);
  });
  await check('audio mode selector switches, persists and restores with a preset',async()=>{
    await evaluate(`document.querySelector('[data-effect="audio"]').click()`);
    await until(`!$('audio-style-field').hidden&&app.params.effect==='audio'`);
    assert.equal(await evaluate(`$('audio-style').value`),'staggered');
    await evaluate(`$('audio-style').value='radial';$('audio-style').dispatchEvent(new Event('change'))`);
    await until(`fetch('/api/state').then(r=>r.json()).then(s=>s.params.audio_style==='radial')`);
    await evaluate(`api('/api/presets',{name:'音频辐射回归'})`);
    await evaluate(`$('audio-style').value='staggered';$('audio-style').dispatchEvent(new Event('change'))`);
    await until(`fetch('/api/state').then(r=>r.json()).then(s=>s.params.audio_style==='staggered')`);
    await evaluate(`api('/api/presets/apply',{name:'音频辐射回归'})`);
    await until(`$('audio-style').value==='radial'`);
    await navigateWorkspace(base+'/#/studio');
    await until(`$('audio-style')?.value==='radial'&&!$('audio-style-field').hidden`);
    await evaluate(`document.querySelector('[data-effect="static"]').click()`);
    await until(`$('audio-style-field').hidden`);
  });
  await check('audio controls fit desktop and compact widths',async()=>{
    await evaluate(`document.querySelector('[data-effect="audio"]').click()`);
    await until(`!$('audio-style-field').hidden`);
    for (const [width,height] of [[1366,768],[390,844]]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
      await sleep(100);
      assert.equal(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),true);
      const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
      writeFileSync(join(out,`audio-${width}.png`),Buffer.from(shot.data,'base64'));
    }
    await send('Emulation.setDeviceMetricsOverride',{width:1500,height:950,deviceScaleFactor:1,mobile:false});
  });
  await check('sharing captures queued paint edits and exports a complete code',async()=>{
    await evaluate(`api('/api/params',{effect:'paint',brightness:.48,speed:.7})`);
    await evaluate(`pendingPaint.set(22,[123,45,67]);$('share-current').click()`);
    await until(`$('share-dialog').open&&$('share-code').value.startsWith('KEYLIGHT1.')&&!$('share-copy').disabled`);
    assert.equal(await evaluate(`$('share-code').readOnly`),true);
    await evaluate(`var sharedPaintCode=$('share-code').value`);
    const inspected=await evaluate(`api('/api/share/inspect',{code:sharedPaintCode})`);
    assert.deepEqual(inspected.snapshot.paint[22],[123,45,67]);
    assert.equal(inspected.snapshot.params.brightness,.48);
    await send('Emulation.setDeviceMetricsOverride',{width:1366,height:768,deviceScaleFactor:1,mobile:false});
    writeFileSync(join(out,'share-export-1366.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    await evaluate(`$('share-close').click()`);
  });
  await check('import inspect and save-only preserve current lighting',async()=>{
    await evaluate(`api('/api/params',{effect:'static'})`);
    const before=await evaluate(`fetch('/api/state').then(r=>r.json()).then(s=>JSON.stringify({params:s.params,revision:s.device.revision}))`);
    await evaluate(`$('share-open-import').click();$('share-code').value=sharedPaintCode.match(/.{1,40}/g).join(String.fromCharCode(10));$('share-code').dispatchEvent(new Event('input'));$('share-inspect').click()`);
    await until(`!$('share-result').hidden`);
    assert.equal(await evaluate(`fetch('/api/state').then(r=>r.json()).then(s=>JSON.stringify({params:s.params,revision:s.device.revision}))`),before);
    await evaluate(`$('share-name').value='分享导入回归'`);
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
    assert.equal(await evaluate(`$('share-dialog').getBoundingClientRect().right<=innerWidth&&$('share-dialog').scrollWidth<=$('share-dialog').clientWidth`),true);
    writeFileSync(join(out,'share-import-390.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    await evaluate(`$('share-save').click()`);
    await until(`$('share-status').textContent.includes('已保存「分享导入回归」')`);
    assert.equal(await evaluate(`app.params.effect`),'static');
    await evaluate(`$('share-close').click()`);
    await send('Emulation.setDeviceMetricsOverride',{width:1500,height:950,deviceScaleFactor:1,mobile:false});
  });
  await check('import-and-apply restores pixels and preserves same-name originals',async()=>{
    await evaluate(`$('share-open-import').click();$('share-code').value=sharedPaintCode;$('share-inspect').click()`);
    await until(`!$('share-result').hidden`);
    await evaluate(`$('share-name').value='分享导入回归';$('share-save-apply').click()`);
    await until(`$('share-status').textContent.includes('已保存并应用')`);
    const result=await evaluate(`fetch('/api/state').then(r=>r.json())`);
    assert.equal(result.params.effect,'paint');
    assert.deepEqual(result.paint[22],[123,45,67]);
    assert.equal(result.params.speed,.7);
    assert.equal(result.params.brightness,.48);
    assert.equal(result.presets.filter(p=>p.name.startsWith('分享导入回归')).length,2);
    await evaluate(`$('share-close').click()`);
  });
  await check('changing an inspected code invalidates the import result',async()=>{
    await evaluate(`$('share-open-import').click();$('share-code').value=sharedPaintCode;$('share-inspect').click()`);
    await until(`!$('share-result').hidden`);
    await evaluate(`$('share-code').value='bad-code';$('share-code').dispatchEvent(new Event('input'))`);
    assert.equal(await evaluate(`$('share-result').hidden`),true);
    await evaluate(`$('share-inspect').click()`);
    await until(`$('share-status').textContent.includes('KEYLIGHT1')`);
    assert.equal(await evaluate(`$('share-result').hidden`),true);
    await evaluate(`$('share-close').click();errorUntil=0`);
  });
  await check('selected preset edits can be shared without applying them',async()=>{
    await evaluate(`selectPreset(app.presets.find(p=>p.name==='涂色回归'));$('pbright').value=.22;$('p-share').click()`);
    await until(`$('share-code').value.startsWith('KEYLIGHT1.')&&!$('share-copy').disabled`);
    const inspected=await evaluate(`api('/api/share/inspect',{code:$('share-code').value})`);
    assert.equal(inspected.snapshot.params.brightness,.22);
    assert.equal(await evaluate(`app.params.brightness`),.48);
    await evaluate(`$('share-close').click()`);
  });
  await check('AI collection selects a draft without changing active lighting',async()=>{
    await evaluate(`location.hash='#/ai'`);
    await until(`document.querySelector('#custom-list button')`);
    await evaluate(`document.querySelector('#custom-list button').click()`);
    await until(`app.aiDraft?.name==='离线AI样例'`);
    assert.notEqual(await evaluate(`app.params.effect`),'ai');
  });
  await check('AI work shares the expression without an API key',async()=>{
    await evaluate(`$('ai-share').click()`);
    await until(`$('share-dialog').open&&$('share-code').value.startsWith('KEYLIGHT1.')`);
    const inspected=await evaluate(`api('/api/share/inspect',{code:$('share-code').value})`);
    assert.equal(inspected.snapshot.params.effect,'ai');
    assert.equal(inspected.snapshot.ai_spec.expression,'hsv(x+t*0.1,0.8,1)');
    assert.equal(JSON.stringify(inspected).includes('api_key'),false);
    await evaluate(`$('share-close').click()`);
  });
  await check('saving current AI preset retains expression',async()=>{
    await evaluate(`window.confirm=()=>true;$('ai-save-apply').click()`);
    await until(`app.params.effect==='ai'`);
    await evaluate(`location.hash='#/studio';$('save-preset').click()`);
    await until(`fetch('/api/state').then(r=>r.json()).then(s=>s.presets.some(p=>p.params.effect==='ai'&&p.ai_spec?.expression))`);
    assert.equal(await evaluate(`app.params.effect`),'ai');
  });
  await check('paint preset UI restores stored pixels',async()=>{
    await evaluate(`location.hash='#/presets'`);
    await until(`app.view==='presets'&&document.querySelector('.preset-card')`);
    await evaluate(`const p=app.presets.find(p=>p.name==='涂色回归');selectPreset(p);$('p-apply').click()`);
    await until(`fetch('/api/state').then(r=>r.json()).then(s=>s.params.effect==='paint'&&s.paint[22][0]===220)`);
  });
  await check('paint preset edit supports zero brightness',async()=>{
    await evaluate(`$('pbright').value=0;$('p-apply').click()`);
    await until(`fetch('/api/state').then(r=>r.json()).then(s=>s.params.brightness===0&&s.paint[22][0]===220)`);
  });
  await check('request failures are visible and preserve current state',async()=>{
    const result=await evaluate(`api('/api/params',{speed:'broken'}).then(()=>false).catch(()=>true)`);
    assert.equal(result,true);
    assert.match(await evaluate(`$('status').textContent`),/失败/);
    assert.equal(await evaluate(`fetch('/api/state').then(r=>r.json()).then(s=>s.params.speed)`),1);
    await evaluate(`errorUntil=0`);
  });
  await check('reload retrieves paint state and zero brightness',async()=>{
    await navigateWorkspace(base+'/#/studio');
    await until(`document.getElementById('brightness')?.value==='0'&&document.querySelector('.card.active')?.dataset.effect==='paint'`);
  });
  await check('native color control updates real parameters without recoloring app chrome',async()=>{
    const accent=await evaluate(`getComputedStyle(document.documentElement).getPropertyValue('--accent')`);
    await evaluate(`$('native-main').value='#AF542C';$('native-main').dispatchEvent(new Event('input'))`);
    await until(`fetch('/api/state').then(r=>r.json()).then(s=>s.params.color.join(',')==='175,84,44')`);
    assert.equal(await evaluate(`$('hex').value`),'#AF542C');
    assert.equal(await evaluate(`getComputedStyle(document.documentElement).getPropertyValue('--accent')`),accent);
  });
  await check('preset selection synchronizes both native color picker and visible swatch',async()=>{
    await evaluate(`selectPreset({name:'Local test',params:{effect:'wave',color:[9,80,170],color2:[40,50,60]}})`);
    assert.equal(await evaluate(`$('native-preset').value`),'#0950aa');
    assert.equal(await evaluate(`$('pswatch').style.backgroundColor`),'rgb(9, 80, 170)');
    assert.equal(await evaluate(`$('native-preset-secondary').value`),'#28323c');
  });
  await check('single send creates an independent preview without applying lighting',async()=>{
    await evaluate(`showView('ai');$('ai-reset').click()`);
    await until(`app.startNew===true`);
    beforeDialogue=await evaluate(`JSON.stringify(app.params)`);
    await evaluate(`$('ai-input').value='深蓝暗底一道白光从左向右扫过';$('ai-send').click()`);
    await until(`aiBusy===true`);
    assert.equal(await evaluate(`$('ai-reset').disabled`),false);
    await until(`!aiBusy&&app.aiDraft?.name==='深海白光'`);
    assert.match(await evaluate(`$('chat-log').textContent`),/从左向右/);
    assert.equal(await evaluate(`JSON.stringify(app.params)`),beforeDialogue);
    assert.equal(await evaluate(`$('ai-compose').hidden`),true);
    assert.equal(await evaluate(`$('ai-input').value`),'');
    assert.equal(await evaluate(`app.aiUndo`),1);
  });
  await check('natural feedback updates preview and undo restores the previous draft',async()=>{
    await evaluate(`$('ai-input').value='慢一点，其他保持不变';$('ai-send').click()`);
    await until(`!aiBusy&&app.aiDraft?.speed===.4`);
    assert.match(await evaluate(`$('chat-log').textContent`),/减慢速度/);
    assert.equal(await evaluate(`app.aiHistory.length`),4);
    assert.equal(await evaluate(`JSON.stringify(app.params)`),beforeDialogue);
    await evaluate(`$('ai-undo').click()`);
    await until(`!aiBusy&&app.aiDraft?.speed===1`);
    assert.equal(await evaluate(`app.aiHistory.length`),2);
    await evaluate(`$('ai-name').value='深海白光收藏';$('ai-save-apply').click()`);
    await until(`$('ai-status').textContent.includes('已保存并应用')&&app.aiSpec.name==='深海白光收藏'`);
    assert.equal(await evaluate(`app.aiHistory.length`),2);
  });
  await check('invalid expression self repairs in the same send without a second generate button',async()=>{
    await evaluate(`$('ai-input').value='自动修正这个动画';$('ai-send').click()`);
    await until(`!aiBusy&&app.creator.job.state==='done'`);
    assert.ok(await evaluate(`app.creator.job.repairs>0`));
    assert.equal(await evaluate(`app.creator.job.calls`),4);
    assert.equal(await evaluate(`app.aiDraft.kind`),'program');
  });
  await check('exhausted repairs preserve the draft and expose retryable feedback',async()=>{
    const before=await evaluate(`JSON.stringify(app.aiDraft)`);
    await evaluate(`$('ai-input').value='测试失败';$('ai-send').click()`);
    await until(`!aiBusy&&app.creator.job.state==='failed'`);
    assert.equal(await evaluate(`JSON.stringify(app.aiDraft)`),before);
    assert.match(await evaluate(`$('chat-log').textContent`),/记录运行反馈/);
    assert.equal(await evaluate(`$('ai-compose').hidden`),false);
    assert.equal(await evaluate(`$('ai-diagnostics-wrap').hidden`),false);
    assert.ok(await evaluate(`!!app.creator.diagnostics.candidate`));
  });
  await check('reload restores draft, failure context and conversation',async()=>{
    const history=await evaluate(`JSON.stringify(app.aiHistory)`);
    await navigateWorkspace(base+'/#/ai');
    await until(`!!app.aiDraft&&!!app.creator.diagnostics`);
    assert.equal(await evaluate(`JSON.stringify(app.aiHistory)`),history);
    assert.equal(await evaluate(`$('ai-undo').disabled`),false);
    writeFileSync(join(out,'ai-failure-recovery.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true})).data,'base64'));
  });
  await check('natural audio design is independently compiled and can be saved and shared',async()=>{
    await evaluate(`$('ai-input').value='保持配色改为随音乐交错律动';$('ai-send').click()`);
    await until(`!aiBusy&&app.aiDraft?.name==='交错音乐'&&app.aiDraft.kind==='program'`);
    await evaluate(`$('ai-save-effect').click()`);
    await until(`app.custom.some(c=>c.name==='交错音乐'&&c.kind==='program')`);
    await evaluate(`$('ai-share').click()`);
    await until(`$('share-dialog').open&&$('share-code').value.startsWith('KEYLIGHT1.')&&!$('share-copy').disabled`);
    const inspected=await evaluate(`api('/api/share/inspect',{code:$('share-code').value})`);
    assert.equal(inspected.snapshot.params.effect,'ai');
    assert.equal(inspected.snapshot.ai_spec.kind,'program');
    assert.equal(inspected.snapshot.params.audio_style,'staggered');
    await evaluate(`$('share-close').click()`);
  });
  await check('simulated music previews the same program without altering physical input state',async()=>{
    const before=await evaluate(`api('/api/state').then(s=>JSON.stringify({params:s.params,history:s.ai_history}))`);
    await evaluate(`$('ai-preview-audio').click()`);
    await until(`$('ai-preview-status').textContent.includes('模拟音乐预览')`);
    assert.equal(await evaluate(`$('ai-preview-audio').getAttribute('aria-pressed')`),'true');
    assert.equal(await evaluate(`api('/api/state').then(s=>JSON.stringify({params:s.params,history:s.ai_history}))`),before);
    await evaluate(`$('ai-preview-clear').click()`);
    assert.equal(await evaluate(`previewAudio`),false);
  });
  await check('AI card and saved selection both open drafts without applying',async()=>{
    const history=await evaluate(`JSON.stringify(app.aiHistory)`);
    await evaluate(`showView('studio');setEffect('paint')`);
    await until(`app.params.effect==='paint'`);
    await evaluate(`document.querySelector('[data-effect="ai"]').click()`);
    await until(`app.view==='ai'&&app.params.effect==='paint'`);
    assert.equal(await evaluate(`app.aiDraft.kind`),'program');
    assert.equal(await evaluate(`JSON.stringify(app.aiHistory)`),history);
    assert.equal(await evaluate(`$('ai-send').textContent.trim()`),'发送');
    assert.equal(await evaluate(`$('ai-status').textContent.includes('操作失败')`),false);
    await evaluate(`Array.from(document.querySelectorAll('.custom-work')).find(c=>c.textContent.includes('交错音乐')).querySelector('[data-action=select]').click()`);
    await until(`app.aiDraft.name==='交错音乐'`);
    assert.equal(await evaluate(`app.params.effect`),'paint');
  });
  await check('single-key creation is a program and simulated preview has no spread',async()=>{
    await evaluate(`$('ai-reset').click()`);
    await until(`app.startNew`);
    await evaluate(`$('ai-input').value='单键亮起十秒，不扩散';$('ai-send').click()`);
    await until(`!aiBusy&&app.aiDraft?.kind==='program'&&app.aiDraft?.name==='十秒单键'`);
    assert.match(await evaluate(`$('ai-intent').textContent`),/十秒/);
    await evaluate(`previewPress(65,true);previewPress(65,false)`);
    await until(`$('ai-preview-status').textContent.includes('模拟按键')`);
    const result=await evaluate(`api('/api/preview',{spec:app.aiDraft,keys:[{vk:65,held:false,age:.2}]})`);
    const bytes=Buffer.from(result.f,'hex');
    const lit=[];for(let i=0;i<132;i++)if(Math.max(...bytes.subarray(i*3,i*3+3)))lit.push(i);
    assert.deepEqual(lit,[68]);
    const canvas=await evaluate(`Array.from($('ai-canvas').getContext('2d').getImageData(0,0,$('ai-canvas').width,$('ai-canvas').height).data).some((v,i)=>i%4!==3&&v>80)`);
    assert.equal(canvas,true);
  });
  await check('preview retrigger preserves the same last-release time as the real hook',async()=>{
    await evaluate(`previewKeys.clear();previewPress(65,true);previewPress(65,false);var previousRelease=previewKeys.get(65).releaseTime;previewPress(65,true)`);
    assert.equal(await evaluate(`previewKeys.get(65).releaseTime===previousRelease`),true);
    await evaluate(`previewPress(65,false);$('ai-preview-clear').click()`);
    assert.equal(await evaluate(`previewKeys.size`),0);
  });
  await check('AI main secondary colors and sliders are applied and saved',async()=>{
    await evaluate(`$('native-ai').value='#285078';$('native-ai').dispatchEvent(new Event('input'));$('native-ai-secondary').value='#14283c';$('native-ai-secondary').dispatchEvent(new Event('input'));$('aispeed').value=.5;$('aispeed').dispatchEvent(new Event('input'));$('aibright').value=.5;$('aibright').dispatchEvent(new Event('input'))`);
    await until(`aiControlsPending===0&&app.aiDraft?.color.join(',')==='40,80,120'&&app.aiDraft.speed===.5&&app.aiDraft.brightness===.5`);
    await evaluate(`$('ai-name').value='我的定制单键';$('ai-save-apply').click()`);
    await until(`app.custom.some(c=>c.name==='我的定制单键')&&app.aiSpec.name==='我的定制单键'`);
    const saved=await evaluate(`app.custom.find(c=>c.name==='我的定制单键')`);
    assert.deepEqual(saved.color,[40,80,120]);assert.deepEqual(saved.color2,[20,40,60]);
    await evaluate(`$('ai-back').click()`);
    await until(`app.view==='studio'`);
    assert.equal(await evaluate(`$('ai-selected-name').textContent`),'我的定制单键');
    await navigateWorkspace(base+'/#/studio');
    await until(`$('ai-selected-name')?.textContent==='我的定制单键'`);
  });
  await check('saved work has a visible delete button and deletion preserves current lighting',async()=>{
    await evaluate(`setEffect('ai');window.confirm=()=>true`);
    await until(`app.view==='ai'`);
    const before=await evaluate(`JSON.stringify(app.aiSpec)`);
    await evaluate(`Array.from(document.querySelectorAll('.custom-work')).find(c=>c.textContent.includes('我的定制单键')).querySelector('[data-action=delete]').click()`);
    await until(`!app.custom.some(c=>c.name==='我的定制单键')`);
    assert.equal(await evaluate(`JSON.stringify(app.aiSpec)`),before);
    assert.equal(await evaluate(`app.params.effect`),'ai');
  });
  await check('cancel prevents late model replies from replacing the preview',async()=>{
    const before=await evaluate(`JSON.stringify(app.aiDraft)`);
    await evaluate(`$('ai-input').value='另做一个白光动画';$('ai-send').click()`);
    await until(`aiBusy&&!!app.creator.job.id`);
    await evaluate(`$('ai-cancel').click()`);
    await until(`!aiBusy&&app.creator.job.state==='cancelled'`);
    await sleep(1100);
    assert.equal(await evaluate(`JSON.stringify(app.aiDraft)`),before);
    assert.equal(await evaluate(`api('/api/creator').then(s=>s.job.state)`),'cancelled');
  });
  await check('reset during creation leaves a blank draft even after the request returns',async()=>{
    await evaluate(`$('ai-input').value='做一个缓慢光点';$('ai-send').click()`);
    await until(`aiBusy`);
    await evaluate(`$('ai-reset').click()`);
    await until(`!aiBusy&&!app.aiDraft`);
    await sleep(1100);
    assert.equal(await evaluate(`api('/api/creator').then(s=>s.draft)`),null);
    assert.equal(await evaluate(`app.aiHistory.length`),0);
  });
  await check('new work preserves lighting but resets conversation after reload',async()=>{
    await evaluate(`$('ai-reset').click()`);
    await until(`app.startNew===true`);
    await navigateWorkspace(base+'/#/ai');
    await until(`app.startNew===true&&app.aiHistory.length===0`);
    assert.equal(await evaluate(`$('ai-name').value`),'');
    assert.equal(await evaluate(`$('ai-legacy-note').hidden`),true);
    assert.equal(await evaluate(`app.params.effect`),'ai');
    assert.equal(await evaluate(`$('ai-send').textContent.trim()`),'发送');
    assert.equal(await evaluate(`$('ai-undo').disabled`),true);
  });
  await check('model conversation can explain a plan without composing or changing lights',async()=>{
    const before=await evaluate(`JSON.stringify(app.params)`);
    const undo=await evaluate(`app.aiUndo`);
    await evaluate(`$('ai-input').value='先解释按住和松开的区别，不要改灯效';$('ai-send').click()`);
    await until(`!aiBusy&&$('ai-input').value===''`);
    assert.equal(await evaluate(`JSON.stringify(app.params)`),before);
    assert.equal(await evaluate(`app.aiUndo`),undo);
    assert.match(await evaluate(`$('chat-log').textContent`),/先解释按住和松开的区别/);
    const history=await evaluate(`app.aiHistory`);
    for (const text of ['60','"按键"','{"suggestion":"蓝色"}']) {
      assert.equal(await evaluate(`app.aiHistory=[{role:'assistant',content:${JSON.stringify(text)}}];renderChat();$('chat-log').textContent`),'AI'+text);
    }
    await evaluate(`app.aiHistory=${JSON.stringify(history)};renderChat()`);
  });
  await check('render three views across desktop and compact widths',async()=>{
    await evaluate(`api('/api/params',{effect:'breathe',brightness:.65,color:[35,123,170],speed:.35})`);
    for (const [width,height] of [[1500,950],[1366,768],[1100,800],[900,750],[640,800],[390,844]]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
      for (const view of ['studio','presets','ai']) {
        await evaluate(`showView('${view}')`);
        if(view==='presets') await evaluate(`selectPreset(app.presets[0])`);
        await sleep(160);
        assert.equal(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),true,`${view} overflow at ${width}`);
        if(width===1366 && view==='studio') assert.equal(await evaluate(`document.querySelector('[data-effect="paint"]').getBoundingClientRect().bottom<=innerHeight`),true,'last effect should fit a 1366x768 desktop');
        const shot=await send('Page.captureScreenshot',{format:'png'});
        writeFileSync(join(out,`${view}-${width}.png`),Buffer.from(shot.data,'base64'));
      }
    }
    await send('Emulation.setDeviceMetricsOverride',{width:1500,height:950,deviceScaleFactor:1,mobile:false});
    await evaluate(`showView('studio')`);
  });
  await check('export the original vector app icon through browser rasterization',async()=>{
    const png=await evaluate(`(async()=>{const img=new Image();img.src='/icon.svg';await img.decode();const c=document.createElement('canvas');c.width=256;c.height=256;c.getContext('2d').drawImage(img,0,0,256,256);return c.toDataURL('image/png')})()`);
    writeFileSync(join(out,'icon-256.png'),Buffer.from(png.split(',')[1],'base64'));
  });
  await check('desktop layout fits viewport',async()=>{
    assert.equal(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),true);
    const shot=await send('Page.captureScreenshot',{format:'png'});
    writeFileSync(join(out,'offline-ui.png'),Buffer.from(shot.data,'base64'));
  });
  await check('mapping self-check uses the exact physical layout and debug close preserves work',async()=>{
    await evaluate(`setEffect('breathe')`);
    await until(`app.params.effect==='breathe'`);
    const before=await evaluate(`JSON.stringify(app.params)`);
    await evaluate(`$('keymap-open').click()`);
    await until(`$('keymap-dialog').open&&document.querySelectorAll('.physical-key').length===61`);
    assert.equal(await evaluate(`app.keymap.keys.find(k=>k.code==='KeyA').led`),68);
    assert.equal(await evaluate(`app.keymap.keys.find(k=>k.code==='KeyB').led`),94);
    assert.equal(await evaluate(`app.keymap.keys.some(k=>k.code==='Backquote')`),false);
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    assert.equal(await evaluate(`$('keymap-dialog').open`),true);
    await evaluate(`$('keymap-probe').click()`);
    await until(`$('keymap-status').textContent.includes('先开启单键')`);
    await evaluate(`$('keymap-single').checked=true;$('keymap-single').dispatchEvent(new Event('change'))`);
    await until(`keymapData.single_key===true`);
    await evaluate(`$('keymap-led').value=68;$('keymap-probe').click()`);
    await until(`JSON.stringify(keymapData.sent_leds)==='[68]'`);
    writeFileSync(join(out,'keymap-desktop.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
    assert.equal(await evaluate(`$('keymap-dialog').getBoundingClientRect().right<=innerWidth&&$('keymap-dialog').scrollWidth<=$('keymap-dialog').clientWidth`),true);
    writeFileSync(join(out,'keymap-390.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
    await evaluate(`$('keymap-close').click()`);
    await until(`!$('keymap-dialog').open`);
    assert.equal(await evaluate(`JSON.stringify(app.params)`),before);
    assert.equal((await evaluate(`api('/api/keymap')`)).debug,false);
    await send('Emulation.setDeviceMetricsOverride',{width:1500,height:950,deviceScaleFactor:1,mobile:false});
  });
  await check('calibration swaps exact slots and preview immediately uses the same mapping',async()=>{
    await evaluate(`window.confirm=()=>true`);
    await evaluate(`$('keymap-open').click()`);
    await until(`$('keymap-dialog').open`);
    await evaluate(`$('keymap-key').value='65';$('keymap-led').value=122;$('keymap-save').click()`);
    await until(`$('keymap-status').textContent.includes('Fn')`);
    assert.equal(await evaluate(`keymapData.keys.find(k=>k.vk===65).led`),68);
    await evaluate(`$('keymap-key').value='65';$('keymap-led').value=69;$('keymap-save').click()`);
    await until(`keymapData.calibrated&&keymapData.keys.find(k=>k.vk===65).led===69`);
    assert.equal(await evaluate(`keymapData.keys.find(k=>k.vk===83).led`),68);
    const preview=await evaluate(`api('/api/preview',{spec:{kind:'program',expression:'c1 if key_on else grey(0)'},keys:[{vk:65,held:true,age:0}]})`);
    const pixels=Buffer.from(preview.f,'hex'),lit=[];for(let i=0;i<132;i++)if(Math.max(...pixels.subarray(i*3,i*3+3)))lit.push(i);
    assert.deepEqual(lit,[69]);
    await evaluate(`$('keymap-reset').click()`);
    await until(`!keymapData.calibrated&&keymapData.keys.find(k=>k.vk===65).led===68`);
    await evaluate(`$('keymap-close').click()`);
    await until(`!$('keymap-dialog').open`);
  });
  await check('onboard save stops streaming and unsupported effects explain the limit',async()=>{
    await evaluate(`showView('studio');setEffect('audio')`);
    await until(`$('onboard-hint').textContent.includes('不能保存')`);
    await evaluate(`setEffect('ripple')`);
    await until(`$('onboard-hint').textContent.includes('涟漪可保存')`);
    await evaluate(`document.querySelector('.service-settings').open=true;$('brightness').value=.37;$('brightness').dispatchEvent(new Event('input'));$('onboard-save').click()`);
    await until(`app.device.control==='firmware'`);
    const state=await evaluate(`api('/api/state')`);
    assert.equal(state.onboard.saved.verified,true);
    assert.equal(state.onboard.saved.fields[0],8);
    assert.equal(state.params.brightness,.37);
    writeFileSync(join(out,'onboard-save.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
  });
  await check('onboard save flushes queued paint edits before taking the native snapshot',async()=>{
    await evaluate(`setEffect('paint')`);
    await evaluate(`pendingPaint.set(22,[44,55,66]);paintTimer=setTimeout(flushPaint,4000);$('onboard-save').click()`);
    await until(`app.device.control==='firmware'`);
    const state=await evaluate(`api('/api/state')`);
    assert.deepEqual(state.paint[22],[44,55,66]);
    assert.equal(state.onboard.saved.fields[0],10);
  });
  await check('software effect exits normally, flushes pending parameters and saves to the computer',async()=>{
    await evaluate(`api('/api/effect',{effect:'audio'}).then(refreshState)`);
    await evaluate(`window.exitPrompts=0;window.confirm=()=>{exitPrompts++;return false};window.exitReceipt=null;window.exitBrightness=null;window.beforeExitApi=api;api=async(route,body)=>{const result=await beforeExitApi(route,body);if(route==='/api/shutdown')exitReceipt=result.exit;if(route==='/api/params')exitBrightness=body.brightness;return result;};$('brightness').value=.23;$('brightness').dispatchEvent(new Event('input'))`);
    await evaluate(`$('shutdown').click()`);
    await until(`!!window.exitReceipt`);
    assert.equal(await evaluate(`exitReceipt.saved_to`),'computer');
    assert.equal(await evaluate(`exitReceipt.verified`),false);
    assert.equal(await evaluate(`exitPrompts`),0);
    assert.equal(await evaluate(`exitBrightness`),.23);
    await until(`$('device-name').textContent.includes('中断')`);
  });
  assert.deepEqual(errors,[]);
  writeFileSync(join(out,'browser-results.json'),JSON.stringify({fixture:'FAKE_HID',checks,errors},null,2));
  process.stdout.write(`${checks.length} browser checks passed\n`);
} finally {
  if(ws?.readyState===1){try{await send('Browser.close');}catch{}ws.close();}
  proc.kill();
  const resolved=resolve(profile);
  if(resolved.startsWith(resolve(tmpdir())+'\\')&&basename(resolved).startsWith('aula-ui-check-')){
    try{rmSync(resolved,{recursive:true,force:true,maxRetries:3,retryDelay:100});}catch{}
  }
}
