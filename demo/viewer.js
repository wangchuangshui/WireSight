/* Display only. Coordinates are original points; no interpolation or annotation. */
  window.WirePointView = class PointView {
    constructor(canvas, points, overview) {
      this.canvas=canvas;this.points=points;this.overview=overview;this.selected=0;
      this.context=true;this.extra=false;this.annotated=true;this.pan=[0,0];this.clip=null;this.zoom=1;
      this.yaw=-Math.PI/2;this.pitch=-.65;this.bounds=overview.bounds;
      this.gl=canvas.getContext('webgl',{antialias:true,preserveDrawingBuffer:true});
      if(!this.gl)throw Error('此浏览器不支持三维画布，请查看下方最终投影图。');
      const gl=this.gl;
      const vertex=`attribute vec4 a_point;uniform vec3 u_center,u_right,u_up,u_forward;
        uniform vec2 u_scale,u_range;uniform float u_visible[8],u_dpr,u_annotated;varying vec4 v_color;
        void main(){int id=int(a_point.w+0.5);float visible=0.0;vec3 color=vec3(0.0);
          for(int i=0;i<8;i++){if(id==i)visible=u_visible[i];}
          if(id==0)color=vec3(.40,.48,.54);if(id==1)color=vec3(1.,.42,.42);
          if(id==2)color=vec3(1.,.82,.40);if(id==3)color=vec3(.30,.84,.60);
          if(id==4)color=vec3(.32,.71,1.);if(id==5)color=vec3(.81,.63,1.);
          if(id==6)color=vec3(.22,.84,.84);if(id==7)color=vec3(1.,.67,.45);
          if(u_annotated<.5)color=vec3(.72,.78,.82);vec3 p=a_point.xyz-u_center;
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
      this.uniform={};for(const n of ['center','right','up','forward','scale','range','visible','dpr','annotated'])this.uniform[n]=gl.getUniformLocation(this.program,'u_'+n+(n==='visible'?'[0]':''));
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.enable(gl.DEPTH_TEST);gl.clearColor(.035,.075,.11,1);
      let dragging=null;
      canvas.oncontextmenu=e=>e.preventDefault();canvas.onpointerdown=e=>{dragging=[e.clientX,e.clientY,e.button===2||e.shiftKey];canvas.setPointerCapture(e.pointerId);canvas.focus();};
      canvas.onpointermove=e=>{if(!dragging)return;const dx=e.clientX-dragging[0],dy=e.clientY-dragging[1];if(dragging[2]){this.pan[0]+=dx;this.pan[1]+=dy;}else{this.yaw+=dx*.006;this.pitch=Math.max(-1.55,Math.min(1.55,this.pitch+dy*.006));}dragging=[e.clientX,e.clientY,dragging[2]];this.draw();};
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
      for(let j=0;j<3;j++)center[j]-=(right[j]*this.pan[0]-up[j]*this.pan[1])/scale;gl.uniform3fv(this.uniform.center,center);gl.uniform3fv(this.uniform.right,right);gl.uniform3fv(this.uniform.up,up);gl.uniform3fv(this.uniform.forward,forward);
      gl.uniform2f(this.uniform.scale,2*scale/w,2*scale/h);gl.uniform1f(this.uniform.dpr,dpr);gl.uniform1f(this.uniform.annotated,this.annotated?1:0);
      gl.uniform2fv(this.uniform.range,this.clip||[-1e8,1e8]);
      gl.uniform1fv(this.uniform.visible,[this.context?1:0,...[1,2,3,4,5].map(i=>!this.selected||i===this.selected?1:0),this.extra?1:0,this.extra?1:0]);
      gl.drawArrays(gl.POINTS,0,this.points.length/4);
      c.dataset.drawnPoints=String(this.points.length/4);c.dataset.wire=String(this.selected);c.dataset.ready='true';
    }
    select(id){this.pan=[0,0];this.selected=id;this.clip=null;this.bounds=this.overview.bounds;this.zoom=1;this.draw();}
    focus(id,interval){
      this.selected=id;this.clip=[interval[0]-3,interval[1]+3];this.zoom=1;
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];let count=0;
      for(let i=0;i<this.points.length;i+=4){const p=this.points;if(p[i+3]!==id||p[i+1]<this.clip[0]||p[i+1]>this.clip[1])continue;count++;for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],p[i+j]);hi[j]=Math.max(hi[j],p[i+j]);}}
      if(count)this.bounds=[lo,hi];this.draw();
    }
    region(interval){this.pan=[0,0];this.clip=interval;this.selected=0;this.zoom=1;
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];let count=0;
      for(let i=0;i<this.points.length;i+=4){const p=this.points;if(p[i+3]===0||p[i+1]<interval[0]||p[i+1]>interval[1])continue;count++;for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],p[i+j]);hi[j]=Math.max(hi[j],p[i+j]);}}if(count)this.bounds=[lo,hi];this.draw();}
    preset(name){this.pan=[0,0];this.yaw=-Math.PI/2;this.pitch=name==='top'?-Math.PI/2:name==='side'?0:-.65;this.zoom=1;this.draw();}
  }

;
