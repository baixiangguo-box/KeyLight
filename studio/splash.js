/* Local particle sphere. No network, textures, timers or GPU work after entry. */
(() => {
  'use strict';
  const surface = document.getElementById('splash');
  const workspace = document.getElementById('workspace');
  if (!surface || !workspace) return;
  let canvas = document.getElementById('splash-canvas');
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const lowPower = (navigator.hardwareConcurrency || 4) <= 4 || (navigator.deviceMemory || 8) <= 4;
  const listeners = [];
  let phase = 'active', renderer = null, rendererKind = 'static';
  let raf = 0, finishTimer = 0, frames = 0, count = 0, width = 1, height = 1, radius = 1, dpr = 1;
  let clock = 0, previous = 0, slowFrames = 0, exitStarted = 0;
  let touchStart = null, suppressTouchClick = false;
  const entryDuration=1650;
  const entry={progress:0,keyboard:false,rect:null};
  const smooth=(a,b,value)=>{const t=Math.max(0,Math.min(1,(value-a)/(b-a)));return t*t*(3-2*t);};
  function entryProgress(elapsed) {
    // Preserve the initial gathering speed, then smoothly halve the speed for
    // key formation and the crossfade. Position and velocity stay continuous.
    if(elapsed<=250)return Math.max(0,elapsed/1000);
    if(elapsed<=450){const t=(elapsed-250)/1000;return .25+t-1.25*t*t;}
    return Math.min(1,.4+(elapsed-450)/2000);
  }
  const pointer = {x:0,y:0,force:0}, target = {x:0,y:0,force:0};
  let field = null;
  const flow = {x:0,y:0,speed:0};
  const listen = (el,type,fn,options) => { el.addEventListener(type,fn,options); listeners.push(()=>el.removeEventListener(type,fn,options)); };
  const diagnostics = () => ({phase,renderer:rendererKind,particles:count,frames,pendingFrame:!!raf,
    reducedMotion:motion.matches,width,height,dpr,canvasWidth:canvas?.width || 0,
    canvasHeight:canvas?.height || 0,listeners:listeners.length,resourcesReleased:phase==='entered',
    pointer:{...pointer},target:{...target},center:{x:0,y:0},time:clock,lowPower,
    flow:{...flow},surfaceLayers:1,entry:{...entry,rect:entry.rect?{...entry.rect}:null}});
  // Read-only lifecycle information also lets the native-window QA verify cleanup.
  window.keylightSplash = Object.freeze({metrics:diagnostics,sample:()=>field?.sample() || []});

  function stopFrame() { if (raf) cancelAnimationFrame(raf); raf=0; previous=0; }
  function finish() {
    if (phase==='entered') return;
    phase='entered'; entry.progress=1;stopFrame(); clearTimeout(finishTimer); finishTimer=0;
    touchStart=null;
    for (const remove of listeners.splice(0)) remove();
    if (renderer) { renderer.dispose(); renderer=null; }
    field?.dispose();field=null;
    if (canvas) { canvas.width=canvas.height=0; canvas.remove(); canvas=null; }
    surface.remove();
    document.body.classList.remove('splash-active','splash-entering');
    workspace.inert=false; workspace.removeAttribute('inert'); workspace.removeAttribute('aria-hidden');
    const main=workspace.querySelector('main.active') || workspace.querySelector('main');
    if (main) { main.tabIndex=-1; main.focus({preventScroll:true}); }
    window.dispatchEvent(new Event('keylight:entered'));
  }
  function enter(event) {
    event.preventDefault(); event.stopImmediatePropagation();
    if (phase!=='active') return;
    phase='leaving'; exitStarted=performance.now();
    document.body.classList.add('splash-entering'); surface.classList.add('leaving');
    // Never depend on GPU completion, transitionend or backend readiness to enter.
    finishTimer=setTimeout(finish,motion.matches ? 80 : entryDuration);
    entry.rect=keyboardRect();
    entry.keyboard=!!entry.rect&&!motion.matches&&rendererKind!=='static';
    if(entry.keyboard){
      try{field.beginMorph();surface.classList.add('assembling');}catch{entry.keyboard=false;}
    }
    if(!entry.keyboard)surface.classList.add('fade-only');
    schedule();
  }
  function keyboardRect() {
    const board=workspace.querySelector('#view-studio.active #board');
    if(!board)return null;
    const r=board.getBoundingClientRect();
    // Keep the current route and scroll position. A keyboard outside the
    // viewport (e.g. a narrow phone) uses the short fade instead of flying offscreen.
    if(r.width<40||r.height<15||r.left<0||r.top<0||r.right>width+1||r.bottom>height)return null;
    return {x:r.x,y:r.y,width:r.width,height:r.height};
  }
  listen(surface,'click',event=>{
    // Browsers can synthesize a click after a touch drag. A drag explores the
    // globe; only a tap enters. The next pointerdown starts a fresh gesture.
    if(suppressTouchClick){event.preventDefault();event.stopImmediatePropagation();return;}
    enter(event);
  },true);
  listen(document,'keydown',event=>{
    if (event.key==='Enter' || event.code==='Space' || event.key===' ') enter(event);
    else if (event.key==='Tab') { event.preventDefault(); surface.focus({preventScroll:true}); }
  },true);
  listen(document,'keyup',event=>{
    if (event.key==='Enter' || event.code==='Space') { event.preventDefault(); event.stopImmediatePropagation(); }
  },true);
  surface.focus({preventScroll:true});

  function leavePointer() { target.force=0; }
  function aimPointer(event) {
    const x=(event.clientX-width/2)/radius;
    const y=(height*.49-event.clientY)/radius;
    // Fade out the interaction beyond the globe, instead of carrying its
    // particles indefinitely. Distance is continuous across the silhouette.
    const distance=Math.hypot(x,y);
    const fade=Math.max(0,Math.min(1,(distance-1.35)/.70));
    target.force=1-fade*fade*(3-2*fade);
    // Ignore tiny hand jitter. Input only sets a destination; it never applies
    // a particle impulse directly at the raw cursor position.
    if(Math.hypot(x-target.x,y-target.y)>.015){target.x=x;target.y=y;}
  }
  listen(surface,'pointerdown',event=>{
    suppressTouchClick=false;
    if(event.pointerType==='touch') {
      touchStart={id:event.pointerId,x:event.clientX,y:event.clientY,moved:0};
      if(phase==='active'&&!motion.matches)aimPointer(event);
    }
  },{passive:true});
  listen(surface,'pointermove',event=>{
    if(touchStart?.id===event.pointerId)touchStart.moved=Math.max(touchStart.moved,Math.hypot(event.clientX-touchStart.x,event.clientY-touchStart.y));
    if (phase!=='active' || motion.matches) return;
    aimPointer(event);
  },{passive:true});
  listen(surface,'pointerleave',leavePointer);
  listen(surface,'pointercancel',()=>{touchStart=null;leavePointer();});
  listen(surface,'pointerup',event=>{
    if(event.pointerType!=='touch')return;
    leavePointer();const tapped=touchStart?.id===event.pointerId&&touchStart.moved<12;
    suppressTouchClick=!tapped;touchStart=null;if(tapped)enter(event);
  });
  listen(window,'blur',leavePointer);

  function seeds(total) {
    const data=new Float32Array(total*4);
    let state=0x51a7c3;
    const random=()=>{state^=state<<13;state^=state>>>17;state^=state<<5;return (state>>>0)/4294967296;};
    for(let i=0;i<total;i++) {
      const y=1-2*random(), phi=random()*Math.PI, r=Math.sqrt(1-y*y);
      data.set([Math.cos(phi)*r,y,Math.sin(phi)*r,random()],i*4);
    }
    return data;
  }
  // One persistent particle pool feeds both renderers. Every visible particle
  // follows the same continuous velocity field at its CURRENT position.
  // Integrating a smooth field avoids translating a fixed patch over a second,
  // stationary shell when the cursor crosses the silhouette or changes direction.
  function particleField() {
    let anchors=seeds(42000),vertices=new Float32Array(42000*4);
    let offsets=new Float32Array(42000*2);
    let diffusion=new Float32Array(42000*2);
    for(let i=0;i<42000;i++){const a=anchors[i*4+3]*Math.PI*2;diffusion[i*2]=Math.cos(a);diffusion[i*2+1]=Math.sin(a);}
    vertices.set(anchors);
    let lastTime=0;
    let origins=null,destinations=null;
    return {get vertices(){return vertices;},dispose(){anchors=vertices=offsets=diffusion=origins=destinations=null;},
      beginMorph(){
        origins=new Float32Array(count*3);destinations=new Float32Array(count*2);
        for(let i=0;i<count;i++){
          const k=i*4,j=i*2,n=i*3,seed=vertices[k+3];
          origins[n]=.5+vertices[k]*radius/width;
          origins[n+1]=.49-vertices[k+1]*radius/height;origins[n+2]=vertices[k+2];
          // Match drawFrameInto's 5 x 22 grid, padding, gaps and rounded keys.
          // Most points trace the key edges; the rest give each key a soft fill.
          const pad=Math.min(9,entry.rect.width*.03),cw=(entry.rect.width-pad*2)/22;
          const ch=(Math.round(entry.rect.width*(5/22)*1.02)-pad*2)/5,gap=Math.max(1,Math.min(2.1,cw*.16));
          const w=cw-gap*2,h=ch-gap*2,round=Math.min(6,w/3);
          const random=number=>{const v=Math.sin((i+1)*number)*43758.5453;return v-Math.floor(v);};
          let x=(random(12.9898)-.5)*w,y=(random(78.233)-.5)*h;
          if(seed<.72){
            const angle=random(39.425)*Math.PI*2,dx=Math.cos(angle),dy=Math.sin(angle);
            const length=Math.min(w*.5/Math.max(.0001,Math.abs(dx)),h*.5/Math.max(.0001,Math.abs(dy)));
            x=dx*length;y=dy*length;
          }
          // Project corner samples onto the rounded rectangle rather than
          // drawing square halos around the real rounded keys.
          const cx=Math.max(-w/2+round,Math.min(w/2-round,x));
          const cy=Math.max(-h/2+round,Math.min(h/2-round,y));
          const distance=Math.hypot(x-cx,y-cy),limit=Math.min(1,round/Math.max(.0001,distance));
          x=cx+(x-cx)*limit;y=cy+(y-cy)*limit;
          destinations[j]=.5+x/w;destinations[j+1]=.5+y/h;
        }
      },
      morph(progress,rect){
        if(!origins||!rect)return;
        const pad=Math.min(9,rect.width*.03),cw=(rect.width-pad*2)/22,ch=(rect.height-pad*2)/5;
        const gap=Math.max(1,Math.min(2.1,cw*.16)),w=cw-gap*2,h=ch-gap*2;
        for(let i=0;i<count;i++){
          const k=i*4,j=i*2,n=i*3,seed=vertices[k+3];
          const delay=.065*((i%22)/21*.6+seed*.4),t=smooth(delay,.62+delay,progress);
          const fromX=origins[n]*width,fromY=origins[n+1]*height;
          const col=i%22,row=Math.floor((i%110)/22);
          const toX=rect.x+pad+col*cw+gap+destinations[j]*w;
          const toY=rect.y+pad+row*ch+gap+destinations[j+1]*h;
          const dx=toX-fromX,dy=toY-fromY,length=Math.max(1,Math.hypot(dx,dy));
          const arc=Math.sin(t*Math.PI)*(1-t)*radius*(.13+seed*.12);
          const x=fromX+dx*t-dy/length*arc,y=fromY+dy*t+dx/length*arc;
          vertices[k]=(x-width*.5)/radius;vertices[k+1]=(height*.49-y)/radius;
          vertices[k+2]=origins[n+2]*(1-t)+.6*t;
        }
      },
      sample(){
        const result=[];
        for(let i=0;i<Math.min(count,256);i++)if(vertices[i*4+2]>.1)result.push({
          id:i,x:vertices[i*4],y:vertices[i*4+1],z:vertices[i*4+2],
          dx:offsets[i*2],dy:offsets[i*2+1]});
        return result;
      },
      advance(time,delta){
        if(delta===0)return;
        const angle=(time-lastTime)*.028,c=Math.cos(angle),s=Math.sin(angle);
        const breath=1+Math.sin(time*.66)*.009;
        const breathing=breath/(1+Math.sin(lastTime*.66)*.009);
        const homeC=Math.cos(time*.028),homeS=Math.sin(time*.028);
        // First-order settling has no oscillation, winding or overshoot.
        const settling=Math.exp(-delta*(.12+6.4*(1-pointer.force)));
        const steps=Math.max(1,Math.ceil(delta/.012)),dt=delta/steps;
        for(let i=0;i<count;i++){
          const k=i*4,j=i*2,x=anchors[k],y=anchors[k+1],z=anchors[k+2];
          let px=(vertices[k]*c-vertices[k+1]*s)*breathing;
          let py=(vertices[k]*s+vertices[k+1]*c)*breathing;
          for(let step=0;step<steps;step++){
            const dx=px-pointer.x,dy=py-pointer.y;
            const r2=dx*dx+dy*dy;
            // Repulsive diffusion keeps the followed patch open rather than
            // compressing it into a bright knot at the cursor. No seed subset,
            // fixed edge anchor, winding force or timed return impulse exists.
            const influence=Math.exp(-r2*2.3)*pointer.force;
            const spread=(.045+Math.min(2.4,flow.speed)*.85);
            // Continuous variation for EVERY particle creates a loose cloud,
            // rather than stretching a coherent edge like a rubber membrane.
            const scatter=Math.min(2.4,flow.speed)*.65;
            px+=(flow.x*.98+dx*spread+diffusion[j]*scatter)*influence*dt;
            py+=(flow.y*.98+dy*spread+diffusion[j+1]*scatter)*influence*dt;
          }
          const homeX=(x*homeC-y*homeS)*breath,homeY=(x*homeS+y*homeC)*breath;
          let ox=(px-homeX)*settling,oy=(py-homeY)*settling;
          // A finite local halo preserves the overall spherical silhouette.
          const length=Math.hypot(ox,oy),limit=Math.min(1,.44/Math.max(.00001,length));
          ox*=limit;oy*=limit;px=homeX+ox;py=homeY+oy;
          offsets[j]=ox;offsets[j+1]=oy;
          vertices[k]=px;vertices[k+1]=py;vertices[k+2]=z;vertices[k+3]=anchors[k+3];
        }
        lastTime=time;
      }
    };
  }
  function webgl() {
    const gl=canvas.getContext('webgl',{alpha:true,antialias:false,depth:false,stencil:false,
      premultipliedAlpha:false,preserveDrawingBuffer:false,powerPreference:'low-power'});
    if (!gl) throw new Error('WebGL unavailable');
    const shaders=[]; let program=null, buffer=null;
    function dispose() {
      if(buffer)gl.deleteBuffer(buffer); if(program)gl.deleteProgram(program);
      for(const shader of shaders)gl.deleteShader(shader);
      buffer=program=null; shaders.length=0;
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    }
    function shader(type,source) {
      const value=gl.createShader(type); shaders.push(value); gl.shaderSource(value,source); gl.compileShader(value);
      if(!gl.getShaderParameter(value,gl.COMPILE_STATUS))throw new Error('Particle shader unavailable');
      return value;
    }
    try {
      const vertex=shader(gl.VERTEX_SHADER,`
        precision highp float;
        attribute vec4 aParticle;
        uniform vec2 uViewport;
        uniform float uRadius, uDpr, uExit;
        varying float vAlpha;
        void main() {
          vec3 p=aParticle.xyz;float seed=aParticle.w;
          // Render the near hemisphere only: no rear shell showing through.
          float visible=smoothstep(0.0,.10,p.z);
          float light=.48+.52*max(0.0,dot(normalize(p),normalize(vec3(-.48,.55,.68))));
          float core=smoothstep(.13,.52,length(p.xy));
          float sphereAlpha=visible*light*(.65+.35*seed)*mix(.24,1.0,core)*1.5;
          float assembly=smoothstep(0.0,.62,uExit);
          vAlpha=mix(sphereAlpha,.68+.22*seed,assembly);
          vAlpha*=1.0-smoothstep(.82,1.0,uExit);
          vec2 screen=p.xy*uRadius;
          gl_Position=vec4(screen.x/(uViewport.x*.5),screen.y/(uViewport.y*.5)+.02,0.0,1.0);
          gl_PointSize=mix((1.20+seed*1.0)*(1.0+max(0.0,p.z)*.12),1.25+seed*.65,assembly)*uDpr;
        }`);
      const fragment=shader(gl.FRAGMENT_SHADER,`
        precision mediump float;
        varying float vAlpha;
        void main(){float d=length(gl_PointCoord-vec2(.5));
          float alpha=(1.0-smoothstep(.10,.5,d))*vAlpha;
          gl_FragColor=vec4(vec3(.96),alpha);}`);
      program=gl.createProgram(); gl.attachShader(program,vertex); gl.attachShader(program,fragment); gl.linkProgram(program);
      if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('Particle program unavailable');
      gl.useProgram(program); buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      gl.bufferData(gl.ARRAY_BUFFER,42000*4*4,gl.DYNAMIC_DRAW);
      const attribute=gl.getAttribLocation(program,'aParticle'); gl.enableVertexAttribArray(attribute); gl.vertexAttribPointer(attribute,4,gl.FLOAT,false,0,0);
      const uniforms=Object.fromEntries(['Viewport','Radius','Dpr','Exit'].map(n=>[n,gl.getUniformLocation(program,'u'+n)]));
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA,gl.ONE); gl.clearColor(0,0,0,0);
      return {kind:'webgl',dispose,draw(time,exit) {
        gl.viewport(0,0,canvas.width,canvas.height);gl.clear(gl.COLOR_BUFFER_BIT);
        gl.bufferSubData(gl.ARRAY_BUFFER,0,field.vertices.subarray(0,count*4));
        gl.uniform2f(uniforms.Viewport,width,height);
        gl.uniform1f(uniforms.Radius,radius);gl.uniform1f(uniforms.Dpr,dpr);gl.uniform1f(uniforms.Exit,exit);
        gl.drawArrays(gl.POINTS,0,count);
      }};
    } catch(error) {dispose();throw error;}
  }
  function canvas2d() {
    const ctx=canvas.getContext('2d',{alpha:true});
    if(!ctx)throw new Error('Canvas unavailable');
    return {kind:'canvas2d',dispose(){},draw(time,exit) {
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
      const data=field.vertices;
      const smooth=(a,b,v)=>{const f=Math.max(0,Math.min(1,(v-a)/(b-a)));return f*f*(3-2*f);};
      for(let bucket=0;bucket<8;bucket++) {
        ctx.beginPath();ctx.fillStyle=`rgba(245,245,245,${(bucket+.5)/8})`;
        for(let i=0;i<count;i++) {
          const k=i*4,px=data[k],py=data[k+1],pz=data[k+2],seed=data[k+3];
          if(pz<=0)continue;
          const length=Math.hypot(px,py,pz)||1;
          const light=.48+.52*Math.max(0,(-px*.48+py*.55+pz*.68)/(length*Math.hypot(.48,.55,.68)));
          const assembly=smooth(0,.62,exit);
          const sphereAlpha=1.5*smooth(0,.1,pz)*light*(.65+.35*seed)*(.24+.76*smooth(.13,.52,Math.hypot(px,py)));
          const alpha=sphereAlpha*(1-assembly)+(.68+.22*seed)*assembly;
          if(Math.min(7,Math.floor(alpha*8))!==bucket)continue;
          const sx=width/2+px*radius,sy=height*.49-py*radius;
          const dot=((1.20+seed)*(1+Math.max(0,pz)*.12)*(1-assembly)+(1.25+seed*.65)*assembly)*.5;
          ctx.moveTo(sx+dot,sy);ctx.arc(sx,sy,dot,0,Math.PI*2);
        }
        ctx.globalAlpha=1-smooth(.82,1,exit);ctx.fill();
      }
      ctx.globalAlpha=1;
    }};
  }
  function staticSvg() {
    const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg');
    svg.setAttribute('viewBox','0 0 800 800');svg.setAttribute('aria-hidden','true');svg.classList.add('splash-static');
    const data=seeds(1800);
    for(let i=0;i<1800;i++) {
      const x=data[i*4],y=data[i*4+1],z=data[i*4+2];if(x*x+y*y<.13)continue;
      const circle=document.createElementNS(ns,'circle');circle.setAttribute('cx',400+x*270);circle.setAttribute('cy',400+y*270);
      if(z<=0)continue;circle.setAttribute('r','.75');circle.setAttribute('fill','white');circle.setAttribute('opacity',.16+(z+1)*.22);svg.appendChild(circle);
    }
    surface.prepend(svg);return {kind:'static',draw(){},dispose(){svg.remove();}};
  }
  function fallback() {
    // A canvas that already owns WebGL cannot also acquire a 2D context.
    const fresh=canvas.cloneNode(false);canvas.replaceWith(fresh);canvas=fresh;
    try {renderer=canvas2d();} catch {renderer=staticSvg();}
    rendererKind=renderer.kind;
    if(phase==='leaving'&&rendererKind==='canvas2d')count=Math.min(count,2800);
  }
  function resize() {
    width=Math.max(1,surface.clientWidth);height=Math.max(1,surface.clientHeight);
    radius=Math.min(width*.38,height*.34,320);
    dpr=Math.min(devicePixelRatio||1,lowPower?1.35:1.8);
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
    if(phase==='active')count=rendererKind==='webgl'?Math.min(lowPower?16000:42000,Math.max(9000,Math.round(width*height/30))):rendererKind==='canvas2d'?(motion.matches?9000:2800):1800;
    if(phase==='active' && !raf)draw();
  }
  function draw(exit=0) { if(renderer){field.advance(motion.matches?0:clock,0);renderer.draw(motion.matches?0:clock,exit);frames++;} }
  function tick(timestamp) {
    raf=0;if(phase==='entered' || document.hidden || motion.matches || rendererKind==='static')return;
    const delta=previous?Math.min(.06,(timestamp-previous)/1000):1/60;
    if(previous && delta>.029)slowFrames++;else slowFrames=Math.max(0,slowFrames-1);
    previous=timestamp;clock+=delta;
    const follow=1-Math.exp(-delta*3.6);
    if(phase==='active'){
    const dx=(target.x-pointer.x)*follow,dy=(target.y-pointer.y)*follow;
    const limit=Math.min(1,delta*3.2/Math.max(.0001,Math.hypot(dx,dy)));
    pointer.x+=dx*limit;pointer.y+=dy*limit;pointer.force+=(target.force-pointer.force)*follow;
    flow.x=dx*limit/delta;flow.y=dy*limit/delta;flow.speed=Math.hypot(flow.x,flow.y);
    field.advance(clock,delta);
    if(slowFrames>24 && count>5500 && rendererKind==='webgl'){count=Math.max(5500,Math.floor(count*.72));slowFrames=0;}
    }
    const exit=phase==='leaving'?entryProgress(performance.now()-exitStarted):0;
    entry.progress=exit;
    if(entry.keyboard){entry.rect=keyboardRect()||entry.rect;field.morph(exit,entry.rect);}
    try {draw(exit);} catch {stopFrame();renderer?.dispose();fallback();resize();}
    if(phase!=='entered' && !document.hidden && !motion.matches && rendererKind!=='static')raf=requestAnimationFrame(tick);
  }
  function schedule() { if(!raf && phase!=='entered' && !document.hidden && !motion.matches && rendererKind!=='static')raf=requestAnimationFrame(tick); }
  listen(window,'resize',resize);
  listen(document,'visibilitychange',()=>{stopFrame();if(!document.hidden){draw();schedule();}});
  listen(window,'pagehide',finish);
  const reducedChanged=()=>{if(phase==='leaving'){finish();return;}stopFrame();leavePointer();pointer.force=0;flow.x=flow.y=flow.speed=0;field?.dispose();field=particleField();resize();schedule();};
  if(motion.addEventListener){listen(motion,'change',reducedChanged);}else{motion.addListener(reducedChanged);listeners.push(()=>motion.removeListener(reducedChanged));}
  field=particleField();
  try {renderer=motion.matches?canvas2d():webgl();rendererKind=renderer.kind;} catch {fallback();}
  listen(canvas,'webglcontextlost',event=>{
    event.preventDefault();if(phase==='entered')return;stopFrame();renderer?.dispose();fallback();resize();schedule();
  });
  resize();schedule();
})();
