/* Frozen raw-point display. This module never selects or connects points. */
window.FinalOverview = (() => {
  const byId = id => document.getElementById(id);
  let key = null, generation = 0, viewer = null;
  const colors = ['#778894','#ff6b6b','#ffd166','#4dd599','#52b6ff','#cfa1ff','#38d5d5','#ffac72'];
  const make = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const number = n => n.toLocaleString('zh-CN');

  class PointView {
    constructor(canvas, points, overview) {
      this.canvas=canvas;this.points=points;this.overview=overview;this.selected=0;
      this.context=false;this.extra=false;this.clip=null;this.zoom=1;
      this.yaw=-Math.PI/2;this.pitch=-.65;this.bounds=overview.bounds;
      this.gl=canvas.getContext('webgl',{antialias:true,preserveDrawingBuffer:true});
      if(!this.gl)throw Error('此浏览器不支持三维画布，请查看下方最终投影图。');
      const gl=this.gl;
      const vertex=`attribute vec4 a_point;uniform vec3 u_center,u_right,u_up,u_forward;
        uniform vec2 u_scale,u_range;uniform float u_visible[8],u_dpr;varying vec4 v_color;
        void main(){int id=int(a_point.w+0.5);float visible=0.0;vec3 color=vec3(0.0);
          for(int i=0;i<8;i++){if(id==i)visible=u_visible[i];}
          if(id==0)color=vec3(.40,.48,.54);if(id==1)color=vec3(1.,.42,.42);
          if(id==2)color=vec3(1.,.82,.40);if(id==3)color=vec3(.30,.84,.60);
          if(id==4)color=vec3(.32,.71,1.);if(id==5)color=vec3(.81,.63,1.);
          if(id==6)color=vec3(.22,.84,.84);if(id==7)color=vec3(1.,.67,.45);
          vec3 p=a_point.xyz-u_center;
          gl_Position=vec4(dot(p,u_right)*u_scale.x,dot(p,u_up)*u_scale.y,-dot(p,u_forward)/2000.,1.);
          if(visible<.5 || a_point.y<u_range.x || a_point.y>u_range.y)gl_Position=vec4(2.,2.,2.,1.);
          gl_PointSize=(id==0?1.0:2.1)*u_dpr;v_color=vec4(color,id==0?.45:1.);
        }`;
      const fragment=`precision mediump float;varying vec4 v_color;void main(){
        if(distance(gl_PointCoord,vec2(.5))>.5)discard;gl_FragColor=v_color;}`;
      const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;};
      this.program=gl.createProgram();gl.attachShader(this.program,shader(gl.VERTEX_SHADER,vertex));gl.attachShader(this.program,shader(gl.FRAGMENT_SHADER,fragment));gl.linkProgram(this.program);
      if(!gl.getProgramParameter(this.program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(this.program));
      gl.useProgram(this.program);this.buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);gl.bufferData(gl.ARRAY_BUFFER,points,gl.STATIC_DRAW);
      const pos=gl.getAttribLocation(this.program,'a_point');gl.enableVertexAttribArray(pos);gl.vertexAttribPointer(pos,4,gl.FLOAT,false,16,0);
      this.uniform={};for(const n of ['center','right','up','forward','scale','range','visible','dpr'])this.uniform[n]=gl.getUniformLocation(this.program,'u_'+n+(n==='visible'?'[0]':''));
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.enable(gl.DEPTH_TEST);gl.clearColor(.035,.075,.11,1);
      let dragging=null;
      canvas.onpointerdown=e=>{dragging=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);canvas.focus();};
      canvas.onpointermove=e=>{if(!dragging)return;this.yaw+=(e.clientX-dragging[0])*.006;this.pitch=Math.max(-1.55,Math.min(1.55,this.pitch+(e.clientY-dragging[1])*.006));dragging=[e.clientX,e.clientY];this.draw();};
      canvas.onpointerup=canvas.onpointercancel=()=>{dragging=null;};
      canvas.onwheel=e=>{e.preventDefault();this.zoom=Math.max(.4,Math.min(35,this.zoom*Math.exp(-e.deltaY*.001)));this.draw();};
      canvas.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-'].includes(e.key))return;e.preventDefault();e.stopPropagation();if(e.key==='ArrowLeft')this.yaw-=.12;if(e.key==='ArrowRight')this.yaw+=.12;if(e.key==='ArrowUp')this.pitch+=.1;if(e.key==='ArrowDown')this.pitch-=.1;if(e.key==='+')this.zoom*=1.15;if(e.key==='-')this.zoom/=1.15;this.draw();};
      this.resize=new ResizeObserver(()=>this.draw());this.resize.observe(canvas);this.draw();
    }
    destroy(){this.resize.disconnect();this.gl.deleteBuffer(this.buffer);this.gl.deleteProgram(this.program);}
    draw(){
      const gl=this.gl,c=this.canvas,dpr=Math.min(2,devicePixelRatio||1),w=c.clientWidth,h=c.clientHeight;if(!w||!h)return;
      c.width=Math.round(w*dpr);c.height=Math.round(h*dpr);gl.viewport(0,0,c.width,c.height);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(this.program);
      const cy=Math.cos(this.yaw),sy=Math.sin(this.yaw),cp=Math.cos(this.pitch),sp=Math.sin(this.pitch);
      const right=[cy,-sy,0],up=[sp*sy,sp*cy,cp],forward=[cp*sy,cp*cy,-sp];
      const lo=this.bounds[0],hi=this.bounds[1],center=lo.map((x,i)=>(x+hi[i])/2),extent=lo.map((x,i)=>(hi[i]-x)/2);
      const projectExtent=b=>extent.reduce((s,x,i)=>s+Math.abs(b[i])*x,0);
      const scale=.87*Math.min(w/(2*Math.max(.1,projectExtent(right))),h/(2*Math.max(.1,projectExtent(up))))*this.zoom;
      gl.uniform3fv(this.uniform.center,center);gl.uniform3fv(this.uniform.right,right);gl.uniform3fv(this.uniform.up,up);gl.uniform3fv(this.uniform.forward,forward);
      gl.uniform2f(this.uniform.scale,2*scale/w,2*scale/h);gl.uniform1f(this.uniform.dpr,dpr);
      gl.uniform2fv(this.uniform.range,this.clip||[-1e8,1e8]);
      gl.uniform1fv(this.uniform.visible,[this.context?1:0,...[1,2,3,4,5].map(i=>!this.selected||i===this.selected?1:0),this.extra?1:0,this.extra?1:0]);
      gl.drawArrays(gl.POINTS,0,this.points.length/4);
      c.dataset.drawnPoints=String(this.points.length/4);c.dataset.wire=String(this.selected);c.dataset.ready='true';
    }
    select(id){this.selected=id;this.clip=null;this.bounds=this.overview.bounds;this.zoom=1;this.draw();}
    focus(id,interval){
      this.selected=id;this.clip=[interval[0]-3,interval[1]+3];this.zoom=1;
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];let count=0;
      for(let i=0;i<this.points.length;i+=4){const p=this.points;if(p[i+3]!==id||p[i+1]<this.clip[0]||p[i+1]>this.clip[1])continue;count++;for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],p[i+j]);hi[j]=Math.max(hi[j],p[i+j]);}}
      if(count)this.bounds=[lo,hi];this.draw();
    }
    preset(name){this.yaw=-Math.PI/2;this.pitch=name==='top'?-Math.PI/2:name==='side'?0:-.65;this.zoom=1;this.draw();}
  }

  async function setRun(run,offline){
    const info=run.final_overview,newKey=run.id+':'+(info?.annotation_sha256||'none');if(key===newKey)return;key=newKey;const serial=++generation;
    const section=byId('final-overview');section.hidden=!info;byId('overview-link').hidden=!info;
    if(viewer){viewer.destroy();viewer=null;}if(!info)return;
    section.dataset.ready='loading';
    const url=p=>offline?p.replace(/^\//,''):p;
    byId('overview-state').textContent='五条均有未决区间';
    byId('overview-count').textContent=`五条主线 ${number(info.main_point_count)} 个已标点 · 另有两条横向线 ${number(info.additional_point_count)} 点`;
    byId('overview-quality').textContent=`全场景 P ${run.metrics.combined.precision_pct.toFixed(4)}% · R ${run.metrics.combined.recall_pct.toFixed(4)}%（含横向线；不是逐线完整率）`;
    byId('overview-note').textContent=info.completeness_note;
    byId('overview-status').textContent='正在载入最终标注点…';
    const cards=byId('wire-cards');cards.replaceChildren();
    const select=id=>{if(!viewer)return;viewer.select(id);sync();};
    for(const row of info.main_wires){
      const card=make('button',undefined,'wire-card');card.type='button';card.dataset.wire=row.id;card.style.setProperty('--wire-color',row.color);
      card.append(make('strong',row.name),make('span',`${number(row.points)} 点`),make('small',`${row.unknown_intervals.length} 处已知未决 · 点击单独查看`));
      card.onclick=()=>select(viewer?.selected===row.id?0:row.id);cards.append(card);
    }
    const body=byId('gap-rows');body.replaceChildren();
    for(const row of info.main_wires){
      const tr=make('tr'),name=make('th',row.name);name.scope='row';name.style.color=row.color;tr.append(name);
      const intervals=make('td');
      for(const gap of [...row.unknown_intervals].sort((a,b)=>a.y_offset_m[0]-b.y_offset_m[0])){const b=make('button',gap.y_offset_m.map(n=>n.toFixed(2)).join('–')+' m','gap-button');b.type='button';b.dataset.wire=row.id;b.onclick=()=>{if(!viewer)return;viewer.focus(row.id,gap.y_offset_m);sync(`查看 ${row.name} 未决区间 ${gap.y_offset_m.map(n=>n.toFixed(2)).join('–')} m；未自动补点。`);byId('final-canvas').scrollIntoView({block:'center',behavior:'smooth'});};intervals.append(b);}
      tr.append(intervals,make('td','未完成逐线完整性验收'));body.append(tr);
    }
    byId('show-extra').checked=false;byId('show-context').checked=false;
    byId('additional-lines').textContent=info.additional_wires.map(r=>`${r.name} ${number(r.points)} 点`).join('；');
    const previews=byId('overview-projections');previews.replaceChildren();
    for(const item of info.previews){const frame=make('figure');const im=make('img');im.src=url(item.url);im.alt=item.label;im.onclick=()=>window.imageDialog(item);frame.append(im,make('figcaption',item.label+' · 原始已选点，未连接缺口'));previews.append(frame);}
    const sync=message=>{
      for(const c of cards.children){const active=!!viewer&&(!viewer.selected||Number(c.dataset.wire)===viewer.selected);c.classList.toggle('active',active);c.setAttribute('aria-pressed',String(active));}
      byId('all-wires').classList.toggle('primary',viewer?.selected===0&&!viewer?.clip);
      const row=info.main_wires.find(r=>r.id===viewer?.selected);
      byId('overview-status').textContent=message||(row?`${row.name} · ${number(row.points)} 个已标点；保留连接处缺口。`:`显示五条主线全部 ${number(info.main_point_count)} 个已标点；没有绘制连接缺口的线。`);
      section.dataset.selectedWire=String(viewer?.selected||0);
    };
    byId('all-wires').onclick=()=>{select(0);viewer?.preset('oblique');};
    byId('show-extra').onchange=e=>{if(viewer){viewer.extra=e.target.checked;viewer.draw();}};
    byId('show-context').onchange=e=>{if(viewer){viewer.context=e.target.checked;viewer.draw();}};
    for(const b of document.querySelectorAll('[data-final-camera]'))b.onclick=()=>viewer?.preset(b.dataset.finalCamera);
    try{
      if(!window.ANNOTATION_POINTS?.[run.id])await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=url(info.data_url);script.onload=resolve;script.onerror=()=>reject(Error('最终点集载入失败；可先查看下方投影图。'));document.head.append(script);});
      if(serial!==generation)return;
      const data=window.ANNOTATION_POINTS[run.id];if(data.annotation_sha256!==info.annotation_sha256)throw Error('最终点集版本与标注不一致。');
      const bytes=Uint8Array.from(atob(data.data),c=>c.charCodeAt(0));const points=new Float32Array(bytes.buffer);
      if(points.length!==data.point_count*4)throw Error('最终点集长度校验失败。');
      viewer=new PointView(byId('final-canvas'),points,info);sync();section.dataset.ready='true';
    }catch(e){if(serial===generation){byId('overview-status').textContent=e.message;section.dataset.ready='fallback';}}
  }
  return {setRun};
})();
